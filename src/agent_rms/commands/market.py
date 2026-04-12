"""Market data commands for agent-rms."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

import click

from ..api_client import ApiClient, CliApiError
from ..output import emit_result
from ..session import load_active_session

_SYMBOL_ORDER = ["TS", "TF", "T", "TL"]
_SYMBOL_TO_TENOR = {"TS": "2Y", "TF": "5Y", "T": "10Y", "TL": "30Y"}
_TENOR_ORDER = ["1M", "3M", "6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "30Y"]
_FUTURE_QUOTE_FIELD_ORDER = [
    "instrument_code",
    "last_price",
    "prev_settle",
    "change_amount",
    "change_pct",
    "volume",
    "open_interest",
    "implied_yield",
    "ctd_code",
    "ctd_yield",
    "basis",
    "irr",
    "irr_spread",
    "timestamp",
]
_SWAP_SPREAD_PAIRS = [
    ("1Y", "2Y", "FR007_IRS 1x2"),
    ("1Y", "5Y", "FR007_IRS 1x5"),
    ("2Y", "5Y", "FR007_IRS 2x5"),
]
_MAIN_CONTRACT_LOOKBACK_DAYS = 45


@click.group()
def market() -> None:
    """市场最新数据：all/future/swap/future_curve/swap_curve/asw_curve。"""


def _parse_iso_ts(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _infer_symbol(code: str) -> str | None:
    normalized = code.strip().upper().split(".")[0]
    if normalized.startswith("TS"):
        return "TS"
    if normalized.startswith("TF"):
        return "TF"
    if normalized.startswith("TL"):
        return "TL"
    if normalized.startswith("T"):
        return "T"
    return None


def _normalize_contract_code(code: Any) -> str:
    return str(code or "").strip().upper().split(".")[0]


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        if parsed != parsed:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _pick_float(item: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        parsed = _to_float(item.get(key))
        if parsed is not None:
            return parsed
    return None


def _convert_units_key_value(key: str, value: Any) -> Any:
    if not isinstance(value, (int, float)):
        return value

    lowered = key.lower()
    if ("basis" in lowered or "spread" in lowered) and not lowered.endswith("_bp"):
        return float(value) * 100.0
    if "irr" in lowered and not lowered.endswith("_pct"):
        return float(value) * 100.0
    return value


def _normalize_units_row(item: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in item.items():
        normalized[key] = _convert_units_key_value(key, value)
    return normalized


def _normalize_units_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_units_row(item) for item in items]


def _order_future_quote_fields(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_rows: list[dict[str, Any]] = []
    for item in items:
        ordered: dict[str, Any] = {}
        for key in _FUTURE_QUOTE_FIELD_ORDER:
            if key in item:
                ordered[key] = item[key]
        for key, value in item.items():
            if key not in ordered:
                ordered[key] = value
        ordered_rows.append(ordered)
    return ordered_rows


def _extract_history_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    return _extract_items(response, key="rows")


def _resolve_latest_history_code(rows: list[dict[str, Any]]) -> str | None:
    sorted_rows = sorted(rows, key=lambda row: _parse_iso_ts(row.get("time")), reverse=True)
    for row in sorted_rows:
        ths_code = _normalize_contract_code(row.get("ths_code"))
        if ths_code:
            return ths_code
    return None


def _resolve_main_contract_codes(
    session: dict[str, Any],
    symbols: list[str],
) -> dict[str, str]:
    if not symbols:
        return {}

    end_time = datetime.now(timezone.utc).replace(microsecond=0)
    start_time = end_time - timedelta(days=_MAIN_CONTRACT_LOOKBACK_DAYS)
    preferred_codes: dict[str, str] = {}
    for symbol in symbols:
        try:
            response = _market_get(
                session,
                "/market/bond_futures/history",
                params={
                    "symbol": symbol,
                    "start_time": start_time.isoformat().replace("+00:00", "Z"),
                    "end_time": end_time.isoformat().replace("+00:00", "Z"),
                },
            )
        except click.ClickException:
            continue
        history_code = _resolve_latest_history_code(_extract_history_rows(response))
        if history_code:
            preferred_codes[symbol] = history_code
    return preferred_codes


def _latest_items_by_symbol(
    items: list[dict[str, Any]],
    preferred_codes: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in items:
        instrument_code = str(item.get("instrument_code") or "")
        symbol = _infer_symbol(instrument_code)
        if not symbol:
            continue

        existing = latest.get(symbol)
        if existing is None:
            latest[symbol] = item
            continue

        existing_code = str(existing.get("instrument_code") or "")
        preferred_code = (
            _normalize_contract_code(preferred_codes.get(symbol))
            if preferred_codes is not None and preferred_codes.get(symbol)
            else ""
        )
        if preferred_code:
            current_matches = _normalize_contract_code(instrument_code) == preferred_code
            existing_matches = _normalize_contract_code(existing_code) == preferred_code
            if current_matches and not existing_matches:
                latest[symbol] = item
                continue
            if existing_matches and not current_matches:
                continue

        current_ts = _parse_iso_ts(item.get("timestamp"))
        prev_ts = _parse_iso_ts(existing.get("timestamp"))
        if current_ts > prev_ts:
            latest[symbol] = item
            continue
        if current_ts == prev_ts and instrument_code > existing_code:
            latest[symbol] = item
    return latest


def _build_future_curve_levels(
    items: list[dict[str, Any]],
    preferred_codes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    latest_map = _latest_items_by_symbol(items, preferred_codes=preferred_codes)
    rows: list[dict[str, Any]] = []
    for symbol in _SYMBOL_ORDER:
        item = latest_map.get(symbol)
        if item is None:
            continue
        implied_yield = _pick_float(item, ["implied_yield", "ths_t_bond_futures_forwardrate_bond", "last_yield"])
        ctd_yield = _pick_float(item, ["ctd_yield", "ths_evaluate_yield_cb_bond"])
        basis = _pick_float(item, ["basis"])
        if basis is None and implied_yield is not None and ctd_yield is not None:
            basis = implied_yield - ctd_yield

        rows.append(
            {
                "symbol": symbol,
                "tenor": _SYMBOL_TO_TENOR.get(symbol),
                "instrument_code": item.get("instrument_code"),
                "implied_yield_pct": implied_yield,
                "ctd_yield_pct": ctd_yield,
                "basis_bp": basis * 100.0 if basis is not None else None,
                "timestamp": item.get("timestamp"),
            }
        )
    return rows


def _build_future_spread_pairs(future_curve_levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    level_by_symbol = {
        str(row.get("symbol")): row
        for row in future_curve_levels
        if row.get("symbol")
    }

    rows: list[dict[str, Any]] = []
    for short_idx in range(len(_SYMBOL_ORDER)):
        for long_idx in range(short_idx + 1, len(_SYMBOL_ORDER)):
            short_symbol = _SYMBOL_ORDER[short_idx]
            long_symbol = _SYMBOL_ORDER[long_idx]
            short_row = level_by_symbol.get(short_symbol)
            long_row = level_by_symbol.get(long_symbol)
            if short_row is None or long_row is None:
                continue

            short_yield = _to_float(short_row.get("implied_yield_pct"))
            long_yield = _to_float(long_row.get("implied_yield_pct"))
            if short_yield is None or long_yield is None:
                continue

            rows.append(
                {
                    "pair": f"Future {short_symbol}x{long_symbol}",
                    "short_symbol": short_symbol,
                    "long_symbol": long_symbol,
                    "short_tenor": short_row.get("tenor"),
                    "long_tenor": long_row.get("tenor"),
                    "short_code": short_row.get("instrument_code"),
                    "long_code": long_row.get("instrument_code"),
                    "short_yield_pct": short_yield,
                    "long_yield_pct": long_yield,
                    "spread_bp": 100.0 * (long_yield - short_yield),
                    "timestamp": long_row.get("timestamp") or short_row.get("timestamp"),
                }
            )
    return rows


def _extract_fr007_tenor(code: str) -> str | None:
    normalized = code.strip().upper()
    if not normalized.startswith("FR007_"):
        return None
    match = re.match(r"^FR007_([0-9]+[MYD])(?:\.|$)", normalized)
    if not match:
        return None
    return match.group(1)


def _build_swap_curve_levels(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_tenor: dict[str, dict[str, Any]] = {}
    for item in items:
        instrument_code = str(item.get("instrument_code") or "")
        tenor = _extract_fr007_tenor(instrument_code)
        if not tenor:
            continue

        existing = latest_by_tenor.get(tenor)
        if existing is None:
            latest_by_tenor[tenor] = item
            continue

        current_ts = _parse_iso_ts(item.get("timestamp"))
        prev_ts = _parse_iso_ts(existing.get("timestamp"))
        if current_ts > prev_ts:
            latest_by_tenor[tenor] = item
            continue
        if current_ts == prev_ts and instrument_code > str(existing.get("instrument_code") or ""):
            latest_by_tenor[tenor] = item

    rows: list[dict[str, Any]] = []
    for tenor in sorted(
        latest_by_tenor.keys(),
        key=lambda value: (_TENOR_ORDER.index(value) if value in _TENOR_ORDER else 999, value),
    ):
        item = latest_by_tenor[tenor]
        rows.append(
            {
                "curve": "FR007",
                "tenor": tenor,
                "instrument_code": item.get("instrument_code"),
                "rate_pct": _to_float(item.get("last_price")),
                "timestamp": item.get("timestamp"),
            }
        )
    return rows


def _build_swap_spread_pairs(swap_curve_levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    level_by_tenor = {
        str(row.get("tenor")): row
        for row in swap_curve_levels
        if row.get("tenor")
    }
    rows: list[dict[str, Any]] = []

    for short_tenor, long_tenor, pair_label in _SWAP_SPREAD_PAIRS:
        short_row = level_by_tenor.get(short_tenor)
        long_row = level_by_tenor.get(long_tenor)
        if short_row is None or long_row is None:
            continue

        short_rate = _to_float(short_row.get("rate_pct"))
        long_rate = _to_float(long_row.get("rate_pct"))
        if short_rate is None or long_rate is None:
            continue

        rows.append(
            {
                "pair": pair_label,
                "curve": "FR007",
                "short_tenor": short_tenor,
                "long_tenor": long_tenor,
                "short_code": short_row.get("instrument_code"),
                "long_code": long_row.get("instrument_code"),
                "short_rate_pct": short_rate,
                "long_rate_pct": long_rate,
                "spread_bp": 100.0 * (long_rate - short_rate),
                "timestamp": long_row.get("timestamp") or short_row.get("timestamp"),
            }
        )
    return rows


def _build_asw_curve(
    future_curve_levels: list[dict[str, Any]],
    swap_curve_levels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    swap_by_tenor = {
        str(row.get("tenor")): row
        for row in swap_curve_levels
        if row.get("tenor")
    }
    rows: list[dict[str, Any]] = []

    for future_row in future_curve_levels:
        tenor = str(future_row.get("tenor") or "")
        swap_row = swap_by_tenor.get(tenor)
        if swap_row is None:
            continue

        future_yield = _to_float(future_row.get("implied_yield_pct"))
        swap_rate = _to_float(swap_row.get("rate_pct"))
        if future_yield is None or swap_rate is None:
            continue

        rows.append(
            {
                "tenor": tenor,
                "symbol": future_row.get("symbol"),
                "future_code": future_row.get("instrument_code"),
                "swap_code": swap_row.get("instrument_code"),
                "future_yield_pct": future_yield,
                "swap_rate_pct": swap_rate,
                "asw_bp": 100.0 * (swap_rate - future_yield),
                "timestamp": swap_row.get("timestamp") or future_row.get("timestamp"),
            }
        )

    rows.sort(
        key=lambda row: (
            _TENOR_ORDER.index(str(row.get("tenor")))
            if str(row.get("tenor")) in _TENOR_ORDER
            else 999
        )
    )
    return rows


def _market_get(session: dict[str, Any], path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    client = ApiClient(base_url=session["market_api_base_url"], access_token=session["access_token"])
    response = client.get(path, params=params)
    if not isinstance(response, dict):
        raise click.ClickException(f"行情接口返回格式错误: {path}")
    if not response.get("ok"):
        raise click.ClickException(f"行情接口返回失败: {path}")
    return response


def _extract_items(response: dict[str, Any], key: str = "items") -> list[dict[str, Any]]:
    data = response.get("data")
    if not isinstance(data, dict):
        return []
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


@market.command("future")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
def future(output: str, profile: str | None) -> None:
    """国债期货最新行情（basis/spread 按 bp，irr 按 %）。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _market_get(session, "/market/bond_futures/latest")
    except CliApiError as exc:
        raise click.ClickException(f"获取 future 失败: {exc}") from exc

    emit_result(
        source="market:/market/bond_futures/latest",
        request={"profile": session["profile"]},
        data=_order_future_quote_fields(_normalize_units_rows(_extract_items(response))),
        output=output,
    )


@market.command("swap")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
def swap(output: str, profile: str | None) -> None:
    """利率互换最新行情（basis/spread 按 bp，irr 按 %）。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _market_get(session, "/market/irs/latest")
    except CliApiError as exc:
        raise click.ClickException(f"获取 swap 失败: {exc}") from exc

    emit_result(
        source="market:/market/irs/latest",
        request={"profile": session["profile"]},
        data=_normalize_units_rows(_extract_items(response)),
        output=output,
    )


@market.command("future_curve")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
def future_curve(output: str, profile: str | None) -> None:
    """期货曲线利差对（与利差分析页面一致）。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _market_get(session, "/market/bond_futures/latest")
    except CliApiError as exc:
        raise click.ClickException(f"获取 future_curve 失败: {exc}") from exc

    preferred_codes = _resolve_main_contract_codes(session, list(_SYMBOL_ORDER))
    future_levels = _build_future_curve_levels(
        _extract_items(response),
        preferred_codes=preferred_codes,
    )
    emit_result(
        source="derived:future_curve_spreads",
        request={"profile": session["profile"]},
        data=_build_future_spread_pairs(future_levels),
        output=output,
    )


@market.command("swap_curve")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
def swap_curve(output: str, profile: str | None) -> None:
    """FR007 互换曲线利差对（1x2/1x5/2x5）。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _market_get(session, "/market/irs/latest")
    except CliApiError as exc:
        raise click.ClickException(f"获取 swap_curve 失败: {exc}") from exc

    swap_levels = _build_swap_curve_levels(_extract_items(response))
    emit_result(
        source="derived:swap_curve_spreads",
        request={"profile": session["profile"]},
        data=_build_swap_spread_pairs(swap_levels),
        output=output,
    )


@market.command("asw_curve")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
def asw_curve(output: str, profile: str | None) -> None:
    """ASW 曲线最新值（ASW=100*(FR007_SWAP-期货隐含收益率)）。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        future_response = _market_get(session, "/market/bond_futures/latest")
        swap_response = _market_get(session, "/market/irs/latest")
    except CliApiError as exc:
        raise click.ClickException(f"获取 asw_curve 失败: {exc}") from exc

    preferred_codes = _resolve_main_contract_codes(session, list(_SYMBOL_ORDER))
    future_levels = _build_future_curve_levels(
        _extract_items(future_response),
        preferred_codes=preferred_codes,
    )
    swap_levels = _build_swap_curve_levels(_extract_items(swap_response))
    emit_result(
        source="derived:asw_curve",
        request={"profile": session["profile"]},
        data=_build_asw_curve(future_levels, swap_levels),
        output=output,
    )


@market.command("all")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
def all_latest(output: str, profile: str | None) -> None:
    """聚合输出全部最新市场数据。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        bonds_resp = _market_get(session, "/market/bonds/latest")
        futures_resp = _market_get(session, "/market/bond_futures/latest")
        swap_resp = _market_get(session, "/market/irs/latest")
    except CliApiError as exc:
        raise click.ClickException(f"获取 market all 失败: {exc}") from exc

    bonds = _normalize_units_rows(_extract_items(bonds_resp))
    futures = _normalize_units_rows(_extract_items(futures_resp))
    swaps = _normalize_units_rows(_extract_items(swap_resp))

    preferred_codes = _resolve_main_contract_codes(session, list(_SYMBOL_ORDER))
    future_levels = _build_future_curve_levels(
        _extract_items(futures_resp),
        preferred_codes=preferred_codes,
    )
    swap_levels = _build_swap_curve_levels(_extract_items(swap_resp))

    emit_result(
        source="market:all",
        request={"profile": session["profile"]},
        data={
            "bonds": bonds,
            "future": _order_future_quote_fields(futures),
            "swap": swaps,
            "future_curve": _build_future_spread_pairs(future_levels),
            "swap_curve": _build_swap_spread_pairs(swap_levels),
            "asw_curve": _build_asw_curve(future_levels, swap_levels),
        },
        output=output,
    )

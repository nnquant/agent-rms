"""History data command for agent-rms."""

from __future__ import annotations

import re
from typing import Any

import click

from ..api_client import ApiClient, CliApiError
from ..output import emit_result
from ..session import load_active_session

_FUTURE_SYMBOL_ORDER = ["TS", "TF", "T", "TL"]
_IRS_SPREAD_PAIRS = [
    ("1Y", "2Y", "FR007_IRS 1x2", "1X2"),
    ("1Y", "5Y", "FR007_IRS 1x5", "1X5"),
    ("2Y", "5Y", "FR007_IRS 2x5", "2X5"),
]


@click.command("history")
@click.option(
    "--type",
    "history_type",
    type=click.Choice(["future_curve", "swap_curve"]),
    required=True,
    help="历史数据类型：future_curve 或 swap_curve",
)
@click.option(
    "--symbol",
    default=None,
    help="期货品种过滤（TS/TF/T/TL）；future_curve 时不传返回全部利差对",
)
@click.option(
    "--pair",
    default=None,
    help="利差对过滤；future_curve 示例：TxTL，swap_curve 示例：1x5",
)
@click.option(
    "--curve",
    default="FR007",
    show_default=True,
    help="互换曲线名称，type=swap_curve 时使用",
)
@click.option(
    "--quote-type",
    default="mid",
    show_default=True,
    help="互换曲线报价类型（mid/bid/ask），type=swap_curve 时使用",
)
@click.option("--start-time", default=None, help="起始时间（ISO8601），type=future_curve 时使用")
@click.option("--end-time", default=None, help="结束时间（ISO8601），type=future_curve 时使用")
@click.option("--start-date", default=None, help="起始日期（YYYY-MM-DD），type=swap_curve 时使用")
@click.option("--end-date", default=None, help="结束日期（YYYY-MM-DD），type=swap_curve 时使用")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def history(
    history_type: str,
    symbol: str | None,
    pair: str | None,
    curve: str,
    quote_type: str,
    start_time: str | None,
    end_time: str | None,
    start_date: str | None,
    end_date: str | None,
    profile: str | None,
    output: str,
) -> None:
    """查询历史数据。"""
    session = load_active_session(profile=profile, require_token=True)
    client = ApiClient(base_url=session["market_api_base_url"], access_token=session["access_token"])

    try:
        if history_type == "future_curve":
            future_pairs = _resolve_future_pairs(symbol=symbol, pair=pair)
            history_by_symbol = _fetch_future_history_by_symbol(
                client=client,
                pairs=future_pairs,
                start_time=start_time,
                end_time=end_time,
            )
            rows: list[dict[str, Any]] = []
            for short_symbol, long_symbol, pair_label in future_pairs:
                rows.extend(
                    _build_future_curve_history_rows(
                        short_symbol=short_symbol,
                        long_symbol=long_symbol,
                        pair_label=pair_label,
                        short_rows=history_by_symbol.get(short_symbol, []),
                        long_rows=history_by_symbol.get(long_symbol, []),
                    )
                )
            rows.sort(key=lambda item: (str(item.get("pair") or ""), str(item.get("time") or "")))
            emit_result(
                source="derived:future_curve_history_spreads",
                request={
                    "profile": session["profile"],
                    "type": history_type,
                    "symbol": (symbol or "").strip().upper() or None,
                    "pair": _normalize_future_pair(pair) if pair else None,
                    "start_time": start_time,
                    "end_time": end_time,
                },
                data=rows,
                output=output,
            )
            return

        params = {
            "curve": (curve or "FR007").strip().upper(),
            "quote_type": (quote_type or "mid").strip().lower(),
            "start_date": start_date,
            "end_date": end_date,
        }
        response = client.get("/market/irs_curve/history", params=params)
        rows = _extract_history_rows(response, error_message="查询 swap_curve 历史失败")
        spread_rows = _build_swap_curve_history_rows(
            rows=rows,
            curve=params["curve"],
            quote_type=params["quote_type"],
            pair=pair,
        )
        emit_result(
            source="derived:swap_curve_history_spreads",
            request={
                "profile": session["profile"],
                "type": history_type,
                "curve": params["curve"],
                "quote_type": params["quote_type"],
                "pair": _normalize_irs_pair_key(pair) if pair else None,
                "start_date": start_date,
                "end_date": end_date,
            },
            data=spread_rows,
            output=output,
        )
    except CliApiError as exc:
        raise click.ClickException(f"历史数据查询失败: {exc}") from exc


def _extract_history_rows(response: Any, error_message: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or not response.get("ok"):
        raise click.ClickException(error_message)
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    rows = data.get("rows") if isinstance(data, dict) and isinstance(data.get("rows"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _normalize_future_symbol(symbol: str | None) -> str | None:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return None
    if normalized not in _FUTURE_SYMBOL_ORDER:
        raise click.ClickException("当传入 --symbol 时，必须为 TS/TF/T/TL")
    return normalized


def _normalize_future_pair(pair: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z]", "", (pair or "")).upper()
    match = re.fullmatch(r"(TS|TF|T|TL)X(TS|TF|T|TL)", normalized)
    if not match:
        raise click.ClickException("future_curve 的 --pair 格式无效，例如：TSxTF、TxTL")
    short_symbol, long_symbol = match.groups()
    short_index = _FUTURE_SYMBOL_ORDER.index(short_symbol)
    long_index = _FUTURE_SYMBOL_ORDER.index(long_symbol)
    if short_index >= long_index:
        raise click.ClickException("future_curve 的 --pair 必须按短端x长端顺序，例如：TSxTF、TxTL")
    return f"{short_symbol}x{long_symbol}"


def _resolve_future_pairs(symbol: str | None, pair: str | None) -> list[tuple[str, str, str]]:
    all_pairs = [
        (short_symbol, long_symbol, f"Future {short_symbol}x{long_symbol}")
        for short_index, short_symbol in enumerate(_FUTURE_SYMBOL_ORDER)
        for long_symbol in _FUTURE_SYMBOL_ORDER[short_index + 1 :]
    ]

    if pair:
        normalized_pair = _normalize_future_pair(pair)
        return [item for item in all_pairs if f"{item[0]}x{item[1]}" == normalized_pair]

    normalized_symbol = _normalize_future_symbol(symbol)
    if normalized_symbol:
        filtered = [
            item
            for item in all_pairs
            if normalized_symbol in {item[0], item[1]}
        ]
        if filtered:
            return filtered

    return all_pairs


def _fetch_future_history_by_symbol(
    client: ApiClient,
    pairs: list[tuple[str, str, str]],
    start_time: str | None,
    end_time: str | None,
) -> dict[str, list[dict[str, Any]]]:
    required_symbols = sorted({symbol for pair in pairs for symbol in pair[:2]})
    history_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol in required_symbols:
        response = client.get(
            "/market/bond_futures/history",
            params={"symbol": symbol, "start_time": start_time, "end_time": end_time},
        )
        history_by_symbol[symbol] = _extract_history_rows(
            response=response,
            error_message=f"查询 future_curve 历史失败 symbol={symbol}",
        )
    return history_by_symbol


def _resolve_future_history_yield(row: dict[str, Any]) -> float | None:
    for key in [
        "ths_t_bond_futures_forwardrate_bond",
        "implied_yield",
        "last_yield",
    ]:
        value = row.get(key)
        try:
            if value is None:
                continue
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed == parsed:
            return parsed
    return None


def _build_future_curve_history_rows(
    short_symbol: str,
    long_symbol: str,
    pair_label: str,
    short_rows: list[dict[str, Any]],
    long_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    short_row_by_time: dict[str, dict[str, Any]] = {}
    for row in short_rows:
        time_value = str(row.get("time") or "").strip()
        if time_value:
            short_row_by_time[time_value] = row

    ordered_long_rows = sorted(long_rows, key=lambda row: str(row.get("time") or ""))
    rows: list[dict[str, Any]] = []
    for long_row in ordered_long_rows:
        time_value = str(long_row.get("time") or "").strip()
        if not time_value:
            continue

        short_row = short_row_by_time.get(time_value)
        if short_row is None:
            continue

        short_yield = _resolve_future_history_yield(short_row)
        long_yield = _resolve_future_history_yield(long_row)
        if short_yield is None or long_yield is None:
            continue

        rows.append(
            {
                "pair": pair_label,
                "time": time_value,
                "short_symbol": short_symbol,
                "long_symbol": long_symbol,
                "short_code": short_row.get("ths_code"),
                "long_code": long_row.get("ths_code"),
                "short_yield_pct": short_yield,
                "long_yield_pct": long_yield,
                "spread_bp": 100.0 * (long_yield - short_yield),
            }
        )
    return rows


def _normalize_irs_pair_key(pair: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", (pair or "")).upper()
    if normalized.startswith("FR007IRS"):
        normalized = normalized[len("FR007IRS") :]
    if normalized not in {"1X2", "1X5", "2X5"}:
        raise click.ClickException("swap_curve 的 --pair 格式无效，例如：1x2、1x5、2x5")
    return normalized


def _build_swap_curve_history_rows(
    rows: list[dict[str, Any]],
    curve: str,
    quote_type: str,
    pair: str | None,
) -> list[dict[str, Any]]:
    selected_pair = _normalize_irs_pair_key(pair) if pair else None

    value_by_date_tenor: dict[str, dict[str, float]] = {}
    instrument_by_date_tenor: dict[str, dict[str, Any]] = {}
    for row in rows:
        date_value = str(row.get("time") or "").strip()
        tenor = str(row.get("tenor") or "").strip().upper()
        if not date_value or not tenor:
            continue

        try:
            parsed = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if parsed != parsed:
            continue

        value_by_date_tenor.setdefault(date_value, {})[tenor] = parsed
        instrument_by_date_tenor.setdefault(date_value, {})[tenor] = row.get("instrument_id")

    spread_rows: list[dict[str, Any]] = []
    for date_value in sorted(value_by_date_tenor.keys()):
        tenor_values = value_by_date_tenor[date_value]
        tenor_instruments = instrument_by_date_tenor.get(date_value, {})
        for short_tenor, long_tenor, label, pair_key in _IRS_SPREAD_PAIRS:
            if selected_pair and pair_key != selected_pair:
                continue
            short_value = tenor_values.get(short_tenor)
            long_value = tenor_values.get(long_tenor)
            if short_value is None or long_value is None:
                continue
            spread_rows.append(
                {
                    "pair": label,
                    "date": date_value,
                    "curve": curve,
                    "quote_type": quote_type,
                    "short_tenor": short_tenor,
                    "long_tenor": long_tenor,
                    "short_instrument_id": tenor_instruments.get(short_tenor),
                    "long_instrument_id": tenor_instruments.get(long_tenor),
                    "short_rate_pct": short_value,
                    "long_rate_pct": long_value,
                    "spread_bp": 100.0 * (long_value - short_value),
                }
            )
    return spread_rows

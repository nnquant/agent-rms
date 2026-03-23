"""Portfolio data commands for agent-rms."""

from __future__ import annotations

from typing import Any

import click

from ..api_client import ApiClient, CliApiError
from ..output import emit_result
from ..session import load_active_session


@click.group()
def portfolio() -> None:
    """组合数据：overview/detail/exposure/performance。"""


def _backend_get(session: dict[str, Any], path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    client = ApiClient(base_url=session["api_base_url"], access_token=session["access_token"])
    response = client.get(path, params=params)
    if not isinstance(response, dict):
        raise click.ClickException(f"后端接口返回格式错误: {path}")
    if not response.get("ok"):
        raise click.ClickException(f"后端接口返回失败: {path}")
    return response


def _resolve_product_code(session: dict[str, Any], name: str) -> tuple[str, str]:
    normalized = name.strip()
    if not normalized:
        raise click.ClickException("--name 不能为空")

    try:
        response = _backend_get(session, "/products")
    except CliApiError as exc:
        raise click.ClickException(f"读取产品列表失败: {exc}") from exc

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    products = data.get("products") if isinstance(data, dict) and isinstance(data.get("products"), list) else []

    normalized_upper = normalized.upper()
    code_matches = [item for item in products if isinstance(item, dict) and str(item.get("product_code") or "").upper() == normalized_upper]
    if len(code_matches) == 1:
        product = code_matches[0]
        return str(product.get("product_code")), str(product.get("product_name") or "")

    name_matches = [item for item in products if isinstance(item, dict) and str(item.get("product_name") or "") == normalized]
    if len(name_matches) == 1:
        product = name_matches[0]
        return str(product.get("product_code")), str(product.get("product_name") or "")

    if len(name_matches) > 1:
        options = ", ".join(str(item.get("product_code")) for item in name_matches)
        raise click.ClickException(f"组合名称存在歧义，请使用产品代码。候选: {options}")

    raise click.ClickException(f"未找到组合: {name}")


def _list_products(session: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        response = _backend_get(session, "/products")
    except CliApiError as exc:
        raise click.ClickException(f"读取产品列表失败: {exc}") from exc

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    products = data.get("products") if isinstance(data, dict) and isinstance(data.get("products"), list) else []
    return [item for item in products if isinstance(item, dict)]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_overview_row(product: dict[str, Any], realtime_data: dict[str, Any]) -> dict[str, Any]:
    payload = realtime_data.get("payload") if isinstance(realtime_data.get("payload"), dict) else {}

    net_asset = _safe_float(payload.get("today_net_asset_value"))
    day_pnl = _safe_float(payload.get("daily_pnl"))
    prev_net_asset = _safe_float(payload.get("prev_net_asset_value"))
    pnl_ratio = payload.get("pnl_ratio")

    has_pnl_ratio = pnl_ratio not in (None, 0, 0.0, "0", "0.0")
    if has_pnl_ratio:
        day_pnl_pct = _safe_float(pnl_ratio) * 100
    else:
        day_pnl_pct = (day_pnl / prev_net_asset) * 100 if prev_net_asset != 0 else 0.0

    return {
        "product_code": product.get("product_code"),
        "product_name": product.get("product_name"),
        "product_short_name": product.get("product_short_name"),
        "status": realtime_data.get("status") or product.get("status"),
        "timestamp": realtime_data.get("timestamp"),
        "net_asset": net_asset,
        "unit_net_value": _safe_float(payload.get("today_unit_value"), default=1.0),
        "day_pnl": day_pnl,
        "day_pnl_pct": day_pnl_pct,
        "week_pnl_pct": _safe_float(payload.get("week_pnl_pct")) * 100,
        "month_pnl_pct": _safe_float(payload.get("month_pnl_pct")) * 100,
        "quarter_pnl_pct": _safe_float(payload.get("quarter_pnl_pct")) * 100,
        "year_pnl_pct": _safe_float(payload.get("year_pnl_pct")) * 100,
        "total_pnl_pct": _safe_float(payload.get("total_pnl_pct")) * 100,
    }


@portfolio.command("overview")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def overview(profile: str | None, output: str) -> None:
    """获取全部组合总览（realtime）。"""
    session = load_active_session(profile=profile, require_token=True)
    products = _list_products(session)

    overview_rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    for product in sorted(products, key=lambda item: str(item.get("product_code") or "")):
        product_code = str(product.get("product_code") or "").strip()
        if not product_code:
            continue
        try:
            response = _backend_get(session, f"/products/{product_code}/realtime")
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            overview_rows.append(_build_overview_row(product=product, realtime_data=data))
        except (CliApiError, click.ClickException) as exc:
            failed_rows.append({"product_code": product_code, "error": str(exc)})

    payload: dict[str, Any] = {"overview": overview_rows}
    if failed_rows:
        payload["errors"] = failed_rows
    emit_result(
        source="backend:/products + /products/{product_code}/realtime",
        request={"profile": session["profile"]},
        data=payload,
        output=output,
    )


@portfolio.command("detail")
@click.option("--name", required=True, help="组合名称或产品代码")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def detail(name: str, profile: str | None, output: str) -> None:
    """获取组合明细（holdings + strategies）。"""
    session = load_active_session(profile=profile, require_token=True)
    product_code, product_name = _resolve_product_code(session, name)
    try:
        holdings_response = _backend_get(session, f"/products/{product_code}/holdings")
        strategies_response = _backend_get(session, f"/products/{product_code}/strategies")
    except CliApiError as exc:
        raise click.ClickException(f"读取组合明细失败: {exc}") from exc

    holdings_data = (
        holdings_response.get("data")
        if isinstance(holdings_response.get("data"), dict)
        else {}
    )
    holdings = (
        holdings_data.get("holdings")
        if isinstance(holdings_data, dict) and isinstance(holdings_data.get("holdings"), list)
        else []
    )

    strategies_data = (
        strategies_response.get("data")
        if isinstance(strategies_response.get("data"), dict)
        else {}
    )
    strategies = (
        strategies_data.get("strategies")
        if isinstance(strategies_data, dict)
        and isinstance(strategies_data.get("strategies"), list)
        else []
    )

    emit_result(
        source=f"backend:/products/{product_code}/holdings + /products/{product_code}/strategies",
        request={"profile": session["profile"], "name": name, "product_code": product_code, "product_name": product_name},
        data={
            "holdings_detail": holdings,
            "strategy_performance": strategies,
        },
        output=output,
    )


@portfolio.command("exposure")
@click.option("--name", required=True, help="组合名称或产品代码")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def exposure(name: str, profile: str | None, output: str) -> None:
    """获取组合风险敞口。"""
    session = load_active_session(profile=profile, require_token=True)
    product_code, product_name = _resolve_product_code(session, name)
    try:
        response = _backend_get(session, f"/products/{product_code}/risk-exposure")
    except CliApiError as exc:
        raise click.ClickException(f"读取风险敞口失败: {exc}") from exc

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    rows = data.get("rows") if isinstance(data, dict) and isinstance(data.get("rows"), list) else []
    emit_result(
        source=f"backend:/products/{product_code}/risk-exposure",
        request={"profile": session["profile"], "name": name, "product_code": product_code, "product_name": product_name},
        data=rows,
        output=output,
    )


@portfolio.command("performance")
@click.option("--name", required=True, help="组合名称或产品代码")
@click.option("--start-date", default=None, help="开始日期 YYYY-MM-DD")
@click.option("--end-date", default=None, help="结束日期 YYYY-MM-DD")
@click.option("--normalize", is_flag=True, default=False, help="是否归一化净值")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def performance(
    name: str,
    start_date: str | None,
    end_date: str | None,
    normalize: bool,
    profile: str | None,
    output: str,
) -> None:
    """获取组合绩效。"""
    session = load_active_session(profile=profile, require_token=True)
    product_code, product_name = _resolve_product_code(session, name)
    params: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "normalize": "true" if normalize else None,
    }

    try:
        response = _backend_get(session, f"/products/{product_code}/performance", params=params)
    except CliApiError as exc:
        raise click.ClickException(f"读取组合绩效失败: {exc}") from exc

    emit_result(
        source=f"backend:/products/{product_code}/performance",
        request={
            "profile": session["profile"],
            "name": name,
            "product_code": product_code,
            "product_name": product_name,
            "start_date": start_date,
            "end_date": end_date,
            "normalize": normalize,
        },
        data=response.get("data"),
        output=output,
    )

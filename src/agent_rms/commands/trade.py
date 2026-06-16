"""Manual futures trade commands for agent-rms."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import click

from ..api_client import ApiClient, CliApiError
from ..output import emit_result
from ..session import load_active_session


TRADE_TIME_EXAMPLE = "2026-06-16T09:30:00+08:00"


@click.group()
def trade() -> None:
    """期货手工交易：create/update/delete。"""


def _validate_code(field_name: str, value: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    example = (
        "agent-rms trade create --product-code PROD001 --trade-code FUT_AGENT_001 "
        "--instrument-code T2606 --account-code ACC001 --strategy-code STR001 "
        f"--trade-time {TRADE_TIME_EXAMPLE} --price 101.25 --quantity 2"
    )
    raise click.ClickException(
        f"{field_name} 不能为空或纯空格。请传入有效代码。示例: {example}"
    )


def _validate_price(price: float) -> float:
    if price > 0:
        return price
    raise click.ClickException(
        "price 必须大于 0。请使用真实成交价格，例如: --price 101.25"
    )


def _validate_quantity(quantity: float) -> float:
    if quantity != 0:
        return quantity
    raise click.ClickException(
        "quantity 不能为 0。买入用正数，卖出用负数，例如: --quantity 2 或 --quantity -2"
    )


def _validate_trade_time(trade_time: str) -> str:
    normalized = trade_time.strip()
    if not normalized:
        raise click.ClickException(
            f"trade_time 不能为空。请使用带 timezone 的 ISO8601 时间，例如: {TRADE_TIME_EXAMPLE}"
        )

    parse_value = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError as exc:
        raise click.ClickException(
            f"trade_time 必须是 ISO8601 时间，例如: {TRADE_TIME_EXAMPLE}"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise click.ClickException(
            f"trade_time 必须包含 timezone，例如: {TRADE_TIME_EXAMPLE}"
        )
    return normalized


def _trade_payload(
    instrument_code: str,
    account_code: str,
    strategy_code: str,
    trade_time: str,
    price: float,
    quantity: float,
) -> dict[str, Any]:
    return {
        "instrument_code": _validate_code("instrument_code", instrument_code),
        "account_code": _validate_code("account_code", account_code),
        "strategy_code": _validate_code("strategy_code", strategy_code),
        "trade_time": _validate_trade_time(trade_time),
        "price": _validate_price(price),
        "quantity": _validate_quantity(quantity),
    }


def _advice_for_error(message: str, status_code: int | None) -> str:
    lowered = message.lower()
    if "only same-day futures trades can be modified" in lowered:
        return "建议: 只能维护当日未结算期货成交。请先查询当日成交，历史错误用新更正成交处理。"
    if "settled futures trades cannot be modified" in lowered:
        return "建议: 已结算成交不能编辑或删除，请走调整流程或新增更正成交。"
    if "only future" in lowered:
        return "建议: 此命令只支持期货合约；IRS 或现券交易请使用对应生命周期入口。"
    if status_code in {401, 403} or "access denied" in lowered or "forbidden" in lowered:
        return "建议: 重新执行 agent-rms auth login，并确认账号具备 create_trade 权限和产品范围。"
    if "product not found" in lowered:
        return "建议: 检查 --product-code，或先用 agent-rms portfolio overview 查看可访问组合。"
    if "account" in lowered and "not found" in lowered:
        return "建议: 检查 --account-code 是否属于该产品。"
    if "strategy" in lowered and "not found" in lowered:
        return "建议: 检查 --strategy-code 是否存在。"
    if "instrument" in lowered and "not found" in lowered:
        return "建议: 检查 --instrument-code 是否为已同步的期货合约。"
    return "建议: 检查输入字段、登录态和后端地址后重试。"


def _raise_with_advice(prefix: str, exc: CliApiError) -> None:
    advice = _advice_for_error(str(exc), exc.status_code)
    raise click.ClickException(f"{prefix}: {exc}\n{advice}") from exc


def _ensure_ok(response: Any, path: str) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise click.ClickException(f"后端接口返回格式错误: {path}")
    if not response.get("ok"):
        raise click.ClickException(f"后端接口返回失败: {path}")
    return response


@trade.command("create")
@click.option("--product-code", required=True, help="产品代码")
@click.option("--trade-code", required=True, help="成交编号，作为幂等键")
@click.option("--instrument-code", required=True, help="期货合约代码")
@click.option("--account-code", required=True, help="账户代码")
@click.option("--strategy-code", required=True, help="策略代码")
@click.option("--trade-time", required=True, help=f"成交时间，例如 {TRADE_TIME_EXAMPLE}")
@click.option("--price", type=float, required=True, help="成交价格，必须大于 0")
@click.option("--quantity", type=float, required=True, help="成交数量，买入为正，卖出为负")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def create(
    product_code: str,
    trade_code: str,
    instrument_code: str,
    account_code: str,
    strategy_code: str,
    trade_time: str,
    price: float,
    quantity: float,
    profile: str | None,
    output: str,
) -> None:
    """创建期货手工成交。"""
    product = _validate_code("product_code", product_code)
    code = _validate_code("trade_code", trade_code)
    request = {
        "trade_code": code,
        **_trade_payload(
            instrument_code=instrument_code,
            account_code=account_code,
            strategy_code=strategy_code,
            trade_time=trade_time,
            price=price,
            quantity=quantity,
        ),
    }
    session = load_active_session(profile=profile, require_token=True)
    path = f"/products/{product}/trades"
    client = ApiClient(base_url=session["api_base_url"], access_token=session["access_token"])
    try:
        response = _ensure_ok(client.post(path, json_body=request), path)
    except CliApiError as exc:
        _raise_with_advice("创建期货成交失败", exc)

    emit_result(
        source=f"backend:{path}",
        request={"profile": session["profile"], "product_code": product, **request},
        data=response.get("data"),
        output=output,
    )


@trade.command("update")
@click.option("--product-code", required=True, help="产品代码")
@click.option("--trade-code", required=True, help="已有成交编号")
@click.option("--instrument-code", required=True, help="期货合约代码")
@click.option("--account-code", required=True, help="账户代码")
@click.option("--strategy-code", required=True, help="策略代码")
@click.option("--trade-time", required=True, help=f"成交时间，例如 {TRADE_TIME_EXAMPLE}")
@click.option("--price", type=float, required=True, help="成交价格，必须大于 0")
@click.option("--quantity", type=float, required=True, help="成交数量，买入为正，卖出为负")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def update(
    product_code: str,
    trade_code: str,
    instrument_code: str,
    account_code: str,
    strategy_code: str,
    trade_time: str,
    price: float,
    quantity: float,
    profile: str | None,
    output: str,
) -> None:
    """修改当日未结算期货成交。"""
    product = _validate_code("product_code", product_code)
    code = _validate_code("trade_code", trade_code)
    request = _trade_payload(
        instrument_code=instrument_code,
        account_code=account_code,
        strategy_code=strategy_code,
        trade_time=trade_time,
        price=price,
        quantity=quantity,
    )
    session = load_active_session(profile=profile, require_token=True)
    path = f"/products/{product}/trades/{code}"
    client = ApiClient(base_url=session["api_base_url"], access_token=session["access_token"])
    try:
        response = _ensure_ok(client.patch(path, json_body=request), path)
    except CliApiError as exc:
        _raise_with_advice("修改期货成交失败", exc)

    emit_result(
        source=f"backend:{path}",
        request={
            "profile": session["profile"],
            "product_code": product,
            "trade_code": code,
            **request,
        },
        data=response.get("data"),
        output=output,
    )


@trade.command("delete")
@click.option("--product-code", required=True, help="产品代码")
@click.option("--trade-code", required=True, help="已有成交编号")
@click.option("--yes", is_flag=True, default=False, help="确认删除目标成交")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def delete(product_code: str, trade_code: str, yes: bool, profile: str | None, output: str) -> None:
    """删除当日未结算期货成交。"""
    product = _validate_code("product_code", product_code)
    code = _validate_code("trade_code", trade_code)
    if not yes:
        raise click.ClickException(
            "删除期货成交必须显式确认。请确认目标 trade_code 后重新执行并添加 --yes。"
        )

    session = load_active_session(profile=profile, require_token=True)
    path = f"/products/{product}/trades/{code}"
    client = ApiClient(base_url=session["api_base_url"], access_token=session["access_token"])
    try:
        response = _ensure_ok(client.delete(path), path)
    except CliApiError as exc:
        _raise_with_advice("删除期货成交失败", exc)

    emit_result(
        source=f"backend:{path}",
        request={"profile": session["profile"], "product_code": product, "trade_code": code},
        data=response.get("data"),
        output=output,
    )

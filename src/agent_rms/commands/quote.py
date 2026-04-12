"""Quote entry commands for agent-rms."""

from __future__ import annotations

from typing import Any

import click

from ..api_client import ApiClient, CliApiError
from ..output import emit_result
from ..session import load_active_session


@click.group()
def quote() -> None:
    """行情录入与查询：draft/submit/list/effective。"""


def _backend_get(
    session: dict[str, Any],
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = ApiClient(
        base_url=session["api_base_url"],
        access_token=session["access_token"],
    )
    response = client.get(path, params=params)
    if not isinstance(response, dict):
        raise click.ClickException(f"后端接口返回格式错误: {path}")
    if not response.get("ok"):
        raise click.ClickException(f"后端接口返回失败: {path}")
    return response


def _backend_post(
    session: dict[str, Any],
    path: str,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = ApiClient(
        base_url=session["api_base_url"],
        access_token=session["access_token"],
    )
    response = client.post(path, json_body=json_body)
    if not isinstance(response, dict):
        raise click.ClickException(f"后端接口返回格式错误: {path}")
    if not response.get("ok"):
        raise click.ClickException(f"后端接口返回失败: {path}")
    return response


def _build_payload(
    template: str,
    last_price: float | None,
    bid_price: float | None,
    ask_price: float | None,
    last_yield: float | None,
    last_clean_price: float | None,
) -> dict[str, float]:
    payload: dict[str, float] = {}
    if template == "irs":
        if last_price is None:
            raise click.ClickException("--last-price 为必填")
        payload["last_price"] = last_price
        if bid_price is not None:
            payload["bid_price"] = bid_price
        if ask_price is not None:
            payload["ask_price"] = ask_price
        return payload

    if last_yield is None:
        raise click.ClickException("--last-yield 为必填")
    payload["last_yield"] = last_yield
    if last_clean_price is not None:
        payload["last_clean_price"] = last_clean_price
    return payload


def _submit_quote_entry(
    mode: str,
    instrument_code: str,
    template: str,
    source: str,
    cover_minutes: int,
    timestamp: str | None,
    last_price: float | None,
    bid_price: float | None,
    ask_price: float | None,
    last_yield: float | None,
    last_clean_price: float | None,
    remark: str | None,
    profile: str | None,
    output: str,
) -> None:
    session = load_active_session(profile=profile, require_token=True)
    payload = _build_payload(
        template=template,
        last_price=last_price,
        bid_price=bid_price,
        ask_price=ask_price,
        last_yield=last_yield,
        last_clean_price=last_clean_price,
    )
    request = {
        "instrument_code": instrument_code,
        "template_type": template,
        "source_type": source,
        "mode": mode,
        "cover_minutes": cover_minutes,
        "timestamp": timestamp,
        "payload": payload,
        "remark": remark,
    }
    try:
        response = _backend_post(session, "/quote-entries", request)
    except CliApiError as exc:
        raise click.ClickException(f"提交行情录入失败: {exc}") from exc

    emit_result(
        source="backend:/quote-entries",
        request={"profile": session["profile"], **request},
        data=response.get("data"),
        output=output,
    )


def _entry_options(function):
    function = click.option(
        "--output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
    )(function)
    function = click.option(
        "--profile",
        default=None,
        help="指定 profile，不传则使用 active_profile",
    )(function)
    function = click.option("--remark", default=None, help="录入备注")(function)
    function = click.option("--last-clean-price", type=float, default=None, help="现券净价")(function)
    function = click.option("--last-yield", type=float, default=None, help="现券收益率")(function)
    function = click.option("--ask-price", type=float, default=None, help="IRS ask")(function)
    function = click.option("--bid-price", type=float, default=None, help="IRS bid")(function)
    function = click.option("--last-price", type=float, default=None, help="IRS 固定利率")(function)
    function = click.option("--timestamp", default=None, help="录入时间 ISO8601")(function)
    function = click.option(
        "--cover-minutes",
        type=int,
        default=10,
        show_default=True,
        help="覆盖分钟数",
    )(function)
    function = click.option(
        "--source",
        type=click.Choice(["manual", "agent"]),
        default="agent",
        show_default=True,
    )(function)
    function = click.option("--template", type=click.Choice(["irs", "bond"]), required=True)(function)
    function = click.option("--instrument-code", required=True, help="标的代码")(function)
    return function


@quote.command("draft")
@_entry_options
def draft(
    instrument_code: str,
    template: str,
    source: str,
    cover_minutes: int,
    timestamp: str | None,
    last_price: float | None,
    bid_price: float | None,
    ask_price: float | None,
    last_yield: float | None,
    last_clean_price: float | None,
    remark: str | None,
    profile: str | None,
    output: str,
) -> None:
    """创建行情录入草稿。"""
    _submit_quote_entry(
        mode="draft",
        instrument_code=instrument_code,
        template=template,
        source=source,
        cover_minutes=cover_minutes,
        timestamp=timestamp,
        last_price=last_price,
        bid_price=bid_price,
        ask_price=ask_price,
        last_yield=last_yield,
        last_clean_price=last_clean_price,
        remark=remark,
        profile=profile,
        output=output,
    )


@quote.command("submit")
@_entry_options
def submit(
    instrument_code: str,
    template: str,
    source: str,
    cover_minutes: int,
    timestamp: str | None,
    last_price: float | None,
    bid_price: float | None,
    ask_price: float | None,
    last_yield: float | None,
    last_clean_price: float | None,
    remark: str | None,
    profile: str | None,
    output: str,
) -> None:
    """直接提交并生效行情录入。"""
    _submit_quote_entry(
        mode="direct",
        instrument_code=instrument_code,
        template=template,
        source=source,
        cover_minutes=cover_minutes,
        timestamp=timestamp,
        last_price=last_price,
        bid_price=bid_price,
        ask_price=ask_price,
        last_yield=last_yield,
        last_clean_price=last_clean_price,
        remark=remark,
        profile=profile,
        output=output,
    )


@quote.command("list")
@click.option("--instrument-code", default=None, help="按标的过滤")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def list_entries(instrument_code: str | None, profile: str | None, output: str) -> None:
    """查看最近行情录入记录。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _backend_get(
            session,
            "/quote-entries",
            params={"instrument_code": instrument_code},
        )
    except CliApiError as exc:
        raise click.ClickException(f"读取行情录入记录失败: {exc}") from exc

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    emit_result(
        source="backend:/quote-entries",
        request={"profile": session["profile"], "instrument_code": instrument_code},
        data=items,
        output=output,
    )


@quote.command("effective")
@click.option("--instrument-code", required=True, help="标的代码")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def effective(instrument_code: str, profile: str | None, output: str) -> None:
    """查看当前有效行情来源。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _backend_get(session, f"/quote-entries/effective/{instrument_code}")
    except CliApiError as exc:
        raise click.ClickException(f"读取有效行情失败: {exc}") from exc

    emit_result(
        source=f"backend:/quote-entries/effective/{instrument_code}",
        request={"profile": session["profile"], "instrument_code": instrument_code},
        data=response.get("data"),
        output=output,
    )


@quote.command("confirm")
@click.option("--entry-id", type=int, required=True, help="草稿 entry_id")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def confirm(entry_id: int, profile: str | None, output: str) -> None:
    """确认一条草稿行情录入。"""
    session = load_active_session(profile=profile, require_token=True)
    try:
        response = _backend_post(session, f"/quote-entries/{entry_id}/confirm")
    except CliApiError as exc:
        raise click.ClickException(f"确认行情录入失败: {exc}") from exc

    emit_result(
        source=f"backend:/quote-entries/{entry_id}/confirm",
        request={"profile": session["profile"], "entry_id": entry_id},
        data=response.get("data"),
        output=output,
    )

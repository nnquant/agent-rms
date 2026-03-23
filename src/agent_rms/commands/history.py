"""History data command for agent-rms."""

from __future__ import annotations

from typing import Any

import click

from ..api_client import ApiClient, CliApiError
from ..output import emit_result
from ..session import load_active_session


@click.command("history")
@click.option("--type", "history_type", type=click.Choice(["future_curve", "swap_curve"]), required=True, help="历史数据类型：future_curve 或 swap_curve")
@click.option("--symbol", default=None, help="期货品种（TS/TF/T/TL），type=future_curve 时必填")
@click.option("--curve", default="FR007", show_default=True, help="互换曲线名称，type=swap_curve 时使用")
@click.option("--quote-type", default="mid", show_default=True, help="互换曲线报价类型（mid/bid/ask），type=swap_curve 时使用")
@click.option("--start-time", default=None, help="起始时间（ISO8601），type=future_curve 时使用")
@click.option("--end-time", default=None, help="结束时间（ISO8601），type=future_curve 时使用")
@click.option("--start-date", default=None, help="起始日期（YYYY-MM-DD），type=swap_curve 时使用")
@click.option("--end-date", default=None, help="结束日期（YYYY-MM-DD），type=swap_curve 时使用")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def history(
    history_type: str,
    symbol: str | None,
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
            normalized_symbol = (symbol or "").strip().upper()
            if normalized_symbol not in {"TS", "TF", "T", "TL"}:
                raise click.ClickException("当 --type future_curve 时，--symbol 必须为 TS/TF/T/TL")

            params: dict[str, Any] = {"symbol": normalized_symbol, "start_time": start_time, "end_time": end_time}
            response = client.get("/market/bond_futures/history", params=params)
            if not isinstance(response, dict) or not response.get("ok"):
                raise click.ClickException("查询 future_curve 历史失败")
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            rows = data.get("rows") if isinstance(data, dict) and isinstance(data.get("rows"), list) else []
            emit_result(
                source="market:/market/bond_futures/history",
                request={"profile": session["profile"], "type": history_type, "symbol": normalized_symbol, "start_time": start_time, "end_time": end_time},
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
        if not isinstance(response, dict) or not response.get("ok"):
            raise click.ClickException("查询 swap_curve 历史失败")

        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        rows = data.get("rows") if isinstance(data, dict) and isinstance(data.get("rows"), list) else []
        emit_result(
            source="market:/market/irs_curve/history",
            request={"profile": session["profile"], "type": history_type, "curve": params["curve"], "quote_type": params["quote_type"], "start_date": start_date, "end_date": end_date},
            data=rows,
            output=output,
        )
    except CliApiError as exc:
        raise click.ClickException(f"历史数据查询失败: {exc}") from exc

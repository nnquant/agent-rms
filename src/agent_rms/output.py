"""Output helpers for agent-rms."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import click


def build_envelope(source: str, request: dict[str, Any], data: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "source": source,
        "request": request,
        "data": data,
        "ts": datetime.utcnow().isoformat() + "Z",
    }


def emit_result(source: str, request: dict[str, Any], data: Any, output: str) -> None:
    envelope = build_envelope(source=source, request=request, data=data)

    if output == "json":
        click.echo(json.dumps(envelope, ensure_ascii=False, indent=2, default=str))
        return

    click.echo(f"source: {source}")
    non_empty_request = {k: v for k, v in request.items() if v not in (None, "", [], {})}
    if non_empty_request:
        click.echo(f"request: {json.dumps(non_empty_request, ensure_ascii=False)}")
    click.echo(f"ts: {envelope['ts']}")
    click.echo()
    click.echo(render_table_block(data))


def render_table_block(data: Any) -> str:
    if isinstance(data, list):
        return _table_from_rows(data)

    if isinstance(data, dict):
        preferred_list_keys = [
            "items",
            "rows",
            "holdings",
            "accounts",
            "strategies",
            "products",
            "trades",
            "snapshots",
            "nav_series",
        ]
        for key in preferred_list_keys:
            value = data.get(key)
            if isinstance(value, list):
                return f"[{key}]\n{_table_from_rows(value)}"

        scalar_items = {k: v for k, v in data.items() if _is_scalar(v)}
        if scalar_items:
            rows = [{"field": k, "value": v} for k, v in scalar_items.items()]
            return _table_from_rows(rows)

        sections: list[str] = []
        for key, value in data.items():
            if isinstance(value, list):
                sections.append(f"[{key}]\n{_table_from_rows(value)}")
            elif isinstance(value, dict):
                rows = [{"field": k, "value": v} for k, v in value.items()]
                sections.append(f"[{key}]\n{_table_from_rows(rows)}")
            else:
                sections.append(f"{key}: {format_scalar(value, key)}")
        return "\n\n".join(sections) if sections else "(empty)"

    return str(data)


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _table_from_rows(rows: list[Any]) -> str:
    normalized_rows = [item for item in rows if isinstance(item, dict)]
    if not normalized_rows:
        return "(empty)" if not rows else "\n".join(str(item) for item in rows)

    headers: list[str] = []
    for row in normalized_rows:
        for key in row.keys():
            if key not in headers:
                headers.append(str(key))

    rendered = [[format_scalar(row.get(header), header) for header in headers] for row in normalized_rows]

    col_widths: list[int] = []
    for index, header in enumerate(headers):
        width = len(str(header))
        for row_values in rendered:
            width = max(width, len(row_values[index]))
        col_widths.append(width)

    def line(ch: str = "-") -> str:
        return "+" + "+".join(ch * (w + 2) for w in col_widths) + "+"

    def render(values: list[str]) -> str:
        cells = []
        for idx, value in enumerate(values):
            if _is_numeric_text(value):
                cells.append(f" {value.rjust(col_widths[idx])} ")
            else:
                cells.append(f" {value.ljust(col_widths[idx])} ")
        return "|" + "|".join(cells) + "|"

    lines = [line("-"), render(headers), line("=")]
    for row in rendered:
        lines.append(render(row))
        lines.append(line("-"))
    return "\n".join(lines)


def _is_numeric_text(text: str) -> bool:
    cleaned = text.replace(",", "").replace("%", "").strip()
    if not cleaned:
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def format_scalar(value: Any, key: str | None = None) -> str:
    if value is None:
        return "--"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value

    normalized_key = (key or "").strip().lower()

    if isinstance(value, int):
        if normalized_key.endswith("_id") or normalized_key in {"id", "user_id", "instrument_id", "holding_id", "trade_id"}:
            return str(value)
        if any(token in normalized_key for token in ["quantity", "qty", "count", "num"]):
            return f"{value:,d}"
        return str(value)

    if isinstance(value, float):
        if any(token in normalized_key for token in [
            "rate", "yield", "basis", "spread", "ratio", "irr", "bp", "return",
            "volatility", "drawdown", "sharpe", "sortino", "calmar",
        ]):
            return f"{value:.4f}"

        if any(token in normalized_key for token in [
            "amount", "pnl", "value", "nav", "asset", "cash", "margin", "notional",
            "price", "cost", "amt", "dv01",
        ]):
            return f"{value:,.2f}"

        if any(token in normalized_key for token in ["quantity", "qty"]):
            return f"{value:,.0f}"

        return f"{value:,.2f}"

    return str(value)

"""Session/profile helpers for agent-rms."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

import click
from jose import jwt

from .credentials import get_active_profile_name, get_profile, load_store


def default_backend_base_url() -> str:
    return os.environ.get("AGENT_RMS_API_BASE_URL", "http://103.47.83.123:8060").strip()


def default_market_base_url() -> str:
    return os.environ.get("AGENT_RMS_MARKET_API_BASE_URL", "http://103.47.83.123:8061").strip()


def decode_token_claims(token: str) -> dict[str, Any]:
    try:
        claims = jwt.get_unverified_claims(token)
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def claim_ts_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def is_token_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc)


def load_active_session(profile: str | None = None, require_token: bool = True) -> dict[str, Any]:
    store = load_store()
    profile_name = profile or get_active_profile_name(store)
    payload = get_profile(store, profile_name)
    if payload is None:
        raise click.ClickException(f"未找到 profile={profile_name} 的登录凭证，请先执行：agent-rms auth login")

    session = {
        "profile": profile_name,
        "api_base_url": payload.get("api_base_url") or default_backend_base_url(),
        "market_api_base_url": payload.get("market_api_base_url") or default_market_base_url(),
        "access_token": payload.get("access_token") or "",
        "username": payload.get("username") or "",
        "role": payload.get("role") or "",
        "user_id": payload.get("user_id"),
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
    }
    if require_token and not session["access_token"]:
        raise click.ClickException("当前 profile 无有效 token，请先执行：agent-rms auth login")
    return session

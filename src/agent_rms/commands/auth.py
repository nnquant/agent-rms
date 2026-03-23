"""Authentication commands for agent-rms."""

from __future__ import annotations

from datetime import datetime, timezone

import click

from ..api_client import ApiClient, CliApiError
from ..credentials import (
    get_active_profile_name,
    get_profile,
    load_store,
    remove_profile,
    save_store,
    upsert_profile,
)
from ..output import emit_result
from ..session import (
    claim_ts_to_iso,
    decode_token_claims,
    default_backend_base_url,
    default_market_base_url,
    is_token_expired,
    load_active_session,
)


@click.group()
def auth() -> None:
    """认证与本地登录态管理（login/status/whoami/logout）。"""


@auth.command("login")
@click.option("--username", help="登录用户名")
@click.option("--password", help="登录密码")
@click.option("--profile", default="default", show_default=True, help="凭证 profile 名称")
@click.option("--api-base-url", default=None, help="业务后端地址，例如 http://103.47.83.123:8060")
@click.option("--market-api-base-url", default=None, help="行情后端地址，例如 http://103.47.83.123:8061")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def login(
    username: str | None,
    password: str | None,
    profile: str,
    api_base_url: str | None,
    market_api_base_url: str | None,
    output: str,
) -> None:
    """登录并在本地保存 token（不会保存明文密码）。"""
    user = (username or "").strip()
    if not user:
        user = click.prompt("username", type=str).strip()
    if not user:
        raise click.ClickException("username 不能为空")

    secret = password
    if not secret:
        secret = click.prompt("password", hide_input=True, type=str)
    if not secret:
        raise click.ClickException("password 不能为空")

    resolved_api = (api_base_url or "").strip() or default_backend_base_url()
    resolved_market_api = (market_api_base_url or "").strip() or default_market_base_url()

    client = ApiClient(resolved_api)
    try:
        response = client.post(
            "/auth/login",
            json_body={
                "username": user,
                "password": secret,
            },
        )
    except CliApiError as exc:
        raise click.ClickException(f"登录失败: {exc}") from exc

    if not isinstance(response, dict) or not response.get("ok"):
        raise click.ClickException("登录失败: 响应格式不正确")

    data = response.get("data")
    if not isinstance(data, dict):
        raise click.ClickException("登录失败: 缺少 data 字段")

    token = str(data.get("access_token") or "")
    if not token:
        raise click.ClickException("登录失败: 缺少 access_token")

    claims = decode_token_claims(token)
    issued_at = claim_ts_to_iso(claims.get("iat")) or datetime.now(timezone.utc).isoformat()
    expires_at = claim_ts_to_iso(claims.get("exp"))

    store = load_store()
    existing = get_profile(store, profile) or {}

    payload = {
        "api_base_url": resolved_api,
        "market_api_base_url": resolved_market_api,
        "access_token": token,
        "token_type": data.get("token_type") or "bearer",
        "username": data.get("username") or user,
        "role": data.get("role") or existing.get("role") or "",
        "user_id": data.get("user_id") or existing.get("user_id"),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    upsert_profile(store, profile, payload)
    save_store(store)

    emit_result(
        source="auth.login",
        request={
            "profile": profile,
            "api_base_url": resolved_api,
            "market_api_base_url": resolved_market_api,
        },
        data={
            "profile": profile,
            "username": payload["username"],
            "role": payload["role"],
            "token_type": payload["token_type"],
            "issued_at": payload["issued_at"],
            "expires_at": payload["expires_at"],
        },
        output=output,
    )


@auth.command("status")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def status(profile: str | None, output: str) -> None:
    """查看本地登录状态。"""
    store = load_store()
    profile_name = profile or get_active_profile_name(store)
    payload = get_profile(store, profile_name)
    if payload is None:
        raise click.ClickException(
            f"未找到 profile={profile_name} 的登录凭证，请先执行：agent-rms auth login"
        )

    expires_at = payload.get("expires_at")
    emit_result(
        source="auth.status",
        request={"profile": profile_name},
        data={
            "profile": profile_name,
            "username": payload.get("username"),
            "role": payload.get("role"),
            "api_base_url": payload.get("api_base_url"),
            "market_api_base_url": payload.get("market_api_base_url"),
            "issued_at": payload.get("issued_at"),
            "expires_at": expires_at,
            "token_expired": is_token_expired(expires_at if isinstance(expires_at, str) else None),
        },
        output=output,
    )


@auth.command("whoami")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def whoami(profile: str | None, output: str) -> None:
    """查看当前 profile 身份，并验证 token 可用性。"""
    session = load_active_session(profile=profile, require_token=True)

    client = ApiClient(
        base_url=session["api_base_url"],
        access_token=session["access_token"],
    )

    product_count = None
    auth_ok = False
    try:
        response = client.get("/products")
        if isinstance(response, dict) and response.get("ok"):
            data = response.get("data")
            if isinstance(data, dict):
                products = data.get("products")
                if isinstance(products, list):
                    product_count = len(products)
            auth_ok = True
    except CliApiError:
        auth_ok = False

    emit_result(
        source="auth.whoami",
        request={"profile": session["profile"]},
        data={
            "profile": session["profile"],
            "username": session["username"],
            "role": session["role"],
            "user_id": session["user_id"],
            "auth_ok": auth_ok,
            "product_count": product_count,
            "expires_at": session["expires_at"],
            "token_expired": is_token_expired(session["expires_at"]),
        },
        output=output,
    )


@auth.command("logout")
@click.option("--profile", default=None, help="指定 profile，不传则使用 active_profile")
@click.option("--output", type=click.Choice(["table", "json"]), default="table", show_default=True)
def logout(profile: str | None, output: str) -> None:
    """删除本地登录态。"""
    store = load_store()
    profile_name = profile or get_active_profile_name(store)

    removed = remove_profile(store, profile_name)
    if not removed:
        raise click.ClickException(f"profile={profile_name} 不存在")

    save_store(store)
    emit_result(
        source="auth.logout",
        request={"profile": profile_name},
        data={"profile": profile_name, "removed": True},
        output=output,
    )

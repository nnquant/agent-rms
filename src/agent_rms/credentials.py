"""Credential storage for agent-rms sessions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PROFILE = "default"


def get_credentials_path() -> Path:
    override = os.environ.get("AGENT_RMS_CREDENTIALS_FILE") or os.environ.get("RMS_CREDENTIALS_FILE")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".rms3" / "credentials.json"


def default_store() -> dict[str, Any]:
    return {"active_profile": DEFAULT_PROFILE, "profiles": {}}


def load_store(path: Path | None = None) -> dict[str, Any]:
    target = path or get_credentials_path()
    if not target.exists():
        return default_store()

    raw = target.read_text(encoding="utf-8").strip()
    if not raw:
        return default_store()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return default_store()

    if not isinstance(parsed, dict):
        return default_store()

    if not isinstance(parsed.get("profiles"), dict):
        parsed["profiles"] = {}
    active = parsed.get("active_profile")
    if not isinstance(active, str) or not active.strip():
        parsed["active_profile"] = DEFAULT_PROFILE
    return parsed


def save_store(store: dict[str, Any], path: Path | None = None) -> None:
    target = path or get_credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(target, 0o600)


def get_active_profile_name(store: dict[str, Any]) -> str:
    value = store.get("active_profile")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_PROFILE


def get_profile(store: dict[str, Any], profile: str | None = None) -> dict[str, Any] | None:
    profiles = store.get("profiles")
    if not isinstance(profiles, dict):
        return None
    profile_name = (profile or get_active_profile_name(store)).strip()
    payload = profiles.get(profile_name)
    return payload if isinstance(payload, dict) else None


def upsert_profile(store: dict[str, Any], profile: str, payload: dict[str, Any]) -> None:
    normalized = profile.strip() or DEFAULT_PROFILE
    profiles = store.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        store["profiles"] = profiles
    profiles[normalized] = payload
    store["active_profile"] = normalized


def remove_profile(store: dict[str, Any], profile: str) -> bool:
    profiles = store.get("profiles")
    if not isinstance(profiles, dict):
        return False
    normalized = profile.strip()
    if not normalized or normalized not in profiles:
        return False

    del profiles[normalized]
    if get_active_profile_name(store) == normalized:
        store["active_profile"] = next(iter(profiles.keys()), DEFAULT_PROFILE)
    return True

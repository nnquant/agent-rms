"""Minimal HTTP JSON client for agent-rms."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class CliApiError(RuntimeError):
    """API error wrapper for CLI commands."""

    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _join_url(base_url: str, path: str) -> str:
    left = base_url.rstrip("/")
    right = path if path.startswith("/") else f"/{path}"
    return f"{left}{right}"


class ApiClient:
    """Simple JSON API client."""

    def __init__(self, base_url: str, access_token: str | None = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = _join_url(self.base_url, path)
        filtered_params = {k: v for k, v in (params or {}).items() if v is not None}
        if filtered_params:
            url = f"{url}?{urlencode(filtered_params, doseq=True)}"

        payload_bytes: bytes | None = None
        if json_body is not None:
            payload_bytes = json.dumps(json_body).encode("utf-8")

        headers = {"Accept": "application/json"}
        if payload_bytes is not None:
            headers["Content-Type"] = "application/json"
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        request = Request(url=url, data=payload_bytes, headers=headers, method=method.upper())

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            payload = None
            message = f"http {exc.code}"
            if body:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = body

            if isinstance(payload, dict):
                detail = payload.get("detail")
                if isinstance(detail, dict):
                    nested = detail.get("error")
                    if isinstance(nested, dict) and nested.get("message"):
                        message = str(nested["message"])
                elif isinstance(detail, str):
                    message = detail
                elif isinstance(payload.get("error"), dict) and payload["error"].get("message"):
                    message = str(payload["error"]["message"])
            raise CliApiError(message, status_code=exc.code, payload=payload) from exc
        except URLError as exc:
            raise CliApiError(f"network error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise CliApiError("invalid json response") from exc

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self.request("POST", path, params=params, json_body=json_body)

    def patch(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self.request("PATCH", path, params=params, json_body=json_body)

    def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("DELETE", path, params=params)

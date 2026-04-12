"""Tests for agent-rms quote entry commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_rms.credentials import save_store
from agent_rms.main import cli


def _save_default_store(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    cred_path = tmp_path / "credentials.json"
    monkeypatch.setenv("AGENT_RMS_CREDENTIALS_FILE", str(cred_path))
    save_store(
        {
            "active_profile": "default",
            "profiles": {
                "default": {
                    "api_base_url": "http://127.0.0.1:8060",
                    "market_api_base_url": "http://127.0.0.1:8061",
                    "access_token": "token",
                }
            },
        },
        path=cred_path,
    )


def test_quote_submit_command(monkeypatch, tmp_path: Path) -> None:
    """quote submit should post a direct effective payload."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_post(self, path, json_body=None, params=None):  # noqa: ANN001
        assert path == "/quote-entries"
        assert params is None
        assert json_body == {
            "instrument_code": "IRS_1Y_RECEIVER",
            "template_type": "irs",
            "source_type": "agent",
            "mode": "direct",
            "cover_minutes": 10,
            "timestamp": None,
            "payload": {
                "last_price": 1.92,
                "bid_price": 1.91,
                "ask_price": 1.93,
            },
            "remark": "agent submit",
        }
        return {"ok": True, "data": {"entry_id": 11, "status": "confirmed"}}

    monkeypatch.setattr("agent_rms.api_client.ApiClient.post", fake_post)

    result = runner.invoke(
        cli,
        [
            "quote",
            "submit",
            "--instrument-code",
            "IRS_1Y_RECEIVER",
            "--template",
            "irs",
            "--last-price",
            "1.92",
            "--bid-price",
            "1.91",
            "--ask-price",
            "1.93",
            "--remark",
            "agent submit",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["entry_id"] == 11
    assert payload["data"]["status"] == "confirmed"


def test_quote_effective_command(monkeypatch, tmp_path: Path) -> None:
    """quote effective should read current effective quote payload."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_get(self, path, params=None):  # noqa: ANN001
        assert path == "/quote-entries/effective/BOND_240210"
        assert params is None
        return {
            "ok": True,
            "data": {
                "instrument_code": "BOND_240210",
                "effective_source": "manual",
                "entry_id": 8,
                "payload": {"last_yield": 1.88},
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.get", fake_get)

    result = runner.invoke(
        cli,
        ["quote", "effective", "--instrument-code", "BOND_240210", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["effective_source"] == "manual"
    assert payload["data"]["entry_id"] == 8


def test_quote_list_command(monkeypatch, tmp_path: Path) -> None:
    """quote list should request quote entry history."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_get(self, path, params=None):  # noqa: ANN001
        assert path == "/quote-entries"
        assert params == {"instrument_code": "IRS_5Y_PAY"}
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "entry_id": 1,
                        "instrument_code": "IRS_5Y_PAY",
                        "status": "draft",
                    }
                ]
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.get", fake_get)

    result = runner.invoke(
        cli,
        ["quote", "list", "--instrument-code", "IRS_5Y_PAY", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"][0]["entry_id"] == 1


def test_quote_confirm_command(monkeypatch, tmp_path: Path) -> None:
    """quote confirm should confirm a draft quote entry."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_post(self, path, json_body=None, params=None):  # noqa: ANN001
        assert path == "/quote-entries/18/confirm"
        assert json_body is None
        assert params is None
        return {"ok": True, "data": {"entry_id": 18, "status": "confirmed"}}

    monkeypatch.setattr("agent_rms.api_client.ApiClient.post", fake_post)

    result = runner.invoke(cli, ["quote", "confirm", "--entry-id", "18", "--output", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["status"] == "confirmed"

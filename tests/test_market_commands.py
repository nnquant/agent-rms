"""Tests for agent-rms market commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_rms.credentials import save_store
from agent_rms.main import cli


def test_market_future_outputs_change_fields(monkeypatch, tmp_path: Path) -> None:
    """agent-rms future command should surface prev_settle and change fields."""
    runner = CliRunner()
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

    def fake_get(self, path, params=None):  # noqa: ANN001
        assert path == "/market/bond_futures/latest"
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "instrument_code": "T2506",
                        "last_price": 100.25,
                        "prev_settle": 99.75,
                        "change_amount": 0.5,
                        "change_pct": 0.5 / 99.75,
                        "timestamp": "2026-03-10T08:00:00Z",
                    }
                ]
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.get", fake_get)

    result = runner.invoke(cli, ["market", "future", "--output", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"][0]["prev_settle"] == 99.75
    assert payload["data"][0]["change_amount"] == 0.5

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


def test_market_all_prefers_main_contract_from_history_for_curve_outputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """market all should derive curve outputs from the latest main contract history."""
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
        if path == "/market/bonds/latest":
            return {"ok": True, "data": {"items": []}}
        if path == "/market/irs/latest":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {
                            "instrument_code": "FR007_2Y.IB",
                            "last_price": 1.55,
                            "timestamp": "2026-04-12T09:30:00Z",
                        },
                        {
                            "instrument_code": "FR007_10Y.IB",
                            "last_price": 1.95,
                            "timestamp": "2026-04-12T09:30:00Z",
                        }
                    ]
                },
            }
        if path == "/market/bond_futures/latest":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {
                            "instrument_code": "TS2606",
                            "last_price": 100.1,
                            "implied_yield": 1.50,
                            "timestamp": "2026-04-12T09:30:00Z",
                        },
                        {
                            "instrument_code": "T2606",
                            "last_price": 99.8,
                            "implied_yield": 1.80,
                            "timestamp": "2026-04-12T09:30:00Z",
                        },
                        {
                            "instrument_code": "T2612",
                            "last_price": 98.2,
                            "implied_yield": 2.20,
                            "timestamp": "2026-04-12T09:30:00Z",
                        },
                    ]
                },
            }
        if path == "/market/bond_futures/history":
            assert params is not None
            if params["symbol"] == "T":
                return {
                    "ok": True,
                    "data": {
                        "rows": [
                            {
                                "time": "2026-04-12T09:00:00Z",
                                "ths_code": "T2606.CFE",
                            }
                        ]
                    },
                }
            return {"ok": True, "data": {"rows": []}}
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr("agent_rms.api_client.ApiClient.get", fake_get)

    result = runner.invoke(cli, ["market", "all", "--output", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    future_curve = payload["data"]["future_curve"]
    asw_curve = payload["data"]["asw_curve"]
    assert future_curve[0]["long_code"] == "T2606"
    assert any(row["future_code"] == "T2606" for row in asw_curve)

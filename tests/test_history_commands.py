"""Tests for agent-rms history commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_rms.credentials import save_store
from agent_rms.main import cli


def test_history_future_curve_outputs_derived_spread_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """future_curve history should emit derived spread rows instead of raw futures rows."""
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
        assert path == "/market/bond_futures/history"
        assert params is not None
        symbol = params["symbol"]
        if symbol == "T":
            return {
                "ok": True,
                "data": {
                    "rows": [
                        {
                            "time": "2026-03-01T00:00:00Z",
                            "ths_code": "T2506.CFE",
                            "ths_t_bond_futures_forwardrate_bond": 2.10,
                        },
                        {
                            "time": "2026-03-02T00:00:00Z",
                            "ths_code": "T2506.CFE",
                            "ths_t_bond_futures_forwardrate_bond": 2.15,
                        },
                    ]
                },
            }
        if symbol == "TL":
            return {
                "ok": True,
                "data": {
                    "rows": [
                        {
                            "time": "2026-03-01T00:00:00Z",
                            "ths_code": "TL2509.CFE",
                            "ths_t_bond_futures_forwardrate_bond": 2.30,
                        },
                        {
                            "time": "2026-03-02T00:00:00Z",
                            "ths_code": "TL2509.CFE",
                            "ths_t_bond_futures_forwardrate_bond": 2.40,
                        },
                    ]
                },
            }
        raise AssertionError(f"unexpected symbol: {symbol}")

    monkeypatch.setattr("agent_rms.api_client.ApiClient.get", fake_get)

    result = runner.invoke(
        cli,
        [
            "history",
            "--type",
            "future_curve",
            "--pair",
            "TxTL",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == "derived:future_curve_history_spreads"
    assert payload["request"]["pair"] == "TxTL"
    assert payload["data"] == [
        {
            "pair": "Future TxTL",
            "time": "2026-03-01T00:00:00Z",
            "short_symbol": "T",
            "long_symbol": "TL",
            "short_code": "T2506.CFE",
            "long_code": "TL2509.CFE",
            "short_yield_pct": 2.1,
            "long_yield_pct": 2.3,
            "spread_bp": 19.99999999999997,
        },
        {
            "pair": "Future TxTL",
            "time": "2026-03-02T00:00:00Z",
            "short_symbol": "T",
            "long_symbol": "TL",
            "short_code": "T2506.CFE",
            "long_code": "TL2509.CFE",
            "short_yield_pct": 2.15,
            "long_yield_pct": 2.4,
            "spread_bp": 25.0,
        },
    ]


def test_history_swap_curve_outputs_derived_spread_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """swap_curve history should emit derived IRS spread rows instead of raw tenor rows."""
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
        assert path == "/market/irs_curve/history"
        assert params == {
            "curve": "FR007",
            "quote_type": "mid",
            "start_date": None,
            "end_date": None,
        }
        return {
            "ok": True,
            "data": {
                "rows": [
                    {
                        "time": "2026-03-01",
                        "tenor": "1Y",
                        "instrument_id": "FR007_1Y",
                        "value": 1.50,
                    },
                    {
                        "time": "2026-03-01",
                        "tenor": "5Y",
                        "instrument_id": "FR007_5Y",
                        "value": 1.80,
                    },
                    {
                        "time": "2026-03-02",
                        "tenor": "1Y",
                        "instrument_id": "FR007_1Y",
                        "value": 1.55,
                    },
                    {
                        "time": "2026-03-02",
                        "tenor": "5Y",
                        "instrument_id": "FR007_5Y",
                        "value": 1.95,
                    },
                ]
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.get", fake_get)

    result = runner.invoke(
        cli,
        [
            "history",
            "--type",
            "swap_curve",
            "--pair",
            "1x5",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == "derived:swap_curve_history_spreads"
    assert payload["request"]["pair"] == "1X5"
    assert payload["data"] == [
        {
            "pair": "FR007_IRS 1x5",
            "date": "2026-03-01",
            "curve": "FR007",
            "quote_type": "mid",
            "short_tenor": "1Y",
            "long_tenor": "5Y",
            "short_instrument_id": "FR007_1Y",
            "long_instrument_id": "FR007_5Y",
            "short_rate_pct": 1.5,
            "long_rate_pct": 1.8,
            "spread_bp": 30.000000000000004,
        },
        {
            "pair": "FR007_IRS 1x5",
            "date": "2026-03-02",
            "curve": "FR007",
            "quote_type": "mid",
            "short_tenor": "1Y",
            "long_tenor": "5Y",
            "short_instrument_id": "FR007_1Y",
            "long_instrument_id": "FR007_5Y",
            "short_rate_pct": 1.55,
            "long_rate_pct": 1.95,
            "spread_bp": 39.99999999999999,
        },
    ]

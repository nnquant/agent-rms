"""Tests for agent-rms futures trade commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_rms.api_client import CliApiError
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


def test_trade_create_posts_manual_future_trade(monkeypatch, tmp_path: Path) -> None:
    """trade create should post a manual futures trade payload."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_post(self, path, json_body=None, params=None):  # noqa: ANN001
        assert path == "/products/PROD001/trades"
        assert params is None
        assert json_body == {
            "trade_code": "FUT_AGENT_001",
            "instrument_code": "T2606",
            "account_code": "ACC001",
            "strategy_code": "STR001",
            "trade_time": "2026-06-16T09:30:00+08:00",
            "price": 101.25,
            "quantity": 2.0,
        }
        return {
            "ok": True,
            "data": {
                "trade_code": "FUT_AGENT_001",
                "message": "Trade created successfully",
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.post", fake_post)

    result = runner.invoke(
        cli,
        [
            "trade",
            "create",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_AGENT_001",
            "--instrument-code",
            "T2606",
            "--account-code",
            "ACC001",
            "--strategy-code",
            "STR001",
            "--trade-time",
            "2026-06-16T09:30:00+08:00",
            "--price",
            "101.25",
            "--quantity",
            "2",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == "backend:/products/PROD001/trades"
    assert payload["data"]["trade_code"] == "FUT_AGENT_001"


def test_trade_update_patches_manual_future_trade(monkeypatch, tmp_path: Path) -> None:
    """trade update should patch an existing manual futures trade."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_patch(self, path, json_body=None, params=None):  # noqa: ANN001
        assert path == "/products/PROD001/trades/FUT_TODAY"
        assert params is None
        assert json_body == {
            "instrument_code": "TF2606",
            "account_code": "ACC002",
            "strategy_code": "STR002",
            "trade_time": "2026-06-16T13:15:00+08:00",
            "price": 102.75,
            "quantity": -3.0,
        }
        return {
            "ok": True,
            "data": {
                "trade_code": "FUT_TODAY",
                "message": "Trade updated successfully",
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.patch", fake_patch)

    result = runner.invoke(
        cli,
        [
            "trade",
            "update",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_TODAY",
            "--instrument-code",
            "TF2606",
            "--account-code",
            "ACC002",
            "--strategy-code",
            "STR002",
            "--trade-time",
            "2026-06-16T13:15:00+08:00",
            "--price",
            "102.75",
            "--quantity",
            "-3",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == "backend:/products/PROD001/trades/FUT_TODAY"
    assert payload["data"]["message"] == "Trade updated successfully"


def test_trade_delete_requires_yes_and_deletes_when_confirmed(monkeypatch, tmp_path: Path) -> None:
    """trade delete should require explicit confirmation before deleting."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)
    called = False

    def fake_delete(self, path, params=None):  # noqa: ANN001
        nonlocal called
        called = True
        assert path == "/products/PROD001/trades/FUT_TODAY"
        assert params is None
        return {
            "ok": True,
            "data": {
                "trade_code": "FUT_TODAY",
                "deleted_trade": True,
                "message": "Trade deleted successfully",
            },
        }

    monkeypatch.setattr("agent_rms.api_client.ApiClient.delete", fake_delete)

    missing_yes = runner.invoke(
        cli,
        [
            "trade",
            "delete",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_TODAY",
        ],
    )

    assert missing_yes.exit_code != 0
    assert "--yes" in missing_yes.output
    assert "确认" in missing_yes.output
    assert called is False

    result = runner.invoke(
        cli,
        [
            "trade",
            "delete",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_TODAY",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["deleted_trade"] is True


def test_trade_create_rejects_invalid_local_inputs(monkeypatch, tmp_path: Path) -> None:
    """trade create should reject malformed inputs before HTTP calls."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fail_post(self, path, json_body=None, params=None):  # noqa: ANN001
        raise AssertionError("HTTP call should not be made")

    monkeypatch.setattr("agent_rms.api_client.ApiClient.post", fail_post)

    empty_product = runner.invoke(
        cli,
        [
            "trade",
            "create",
            "--product-code",
            "   ",
            "--trade-code",
            "FUT_AGENT_001",
            "--instrument-code",
            "T2606",
            "--account-code",
            "ACC001",
            "--strategy-code",
            "STR001",
            "--trade-time",
            "2026-06-16T09:30:00+08:00",
            "--price",
            "101.25",
            "--quantity",
            "2",
        ],
    )
    assert empty_product.exit_code != 0
    assert "product_code" in empty_product.output
    assert "示例" in empty_product.output

    invalid_price = runner.invoke(
        cli,
        [
            "trade",
            "create",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_AGENT_001",
            "--instrument-code",
            "T2606",
            "--account-code",
            "ACC001",
            "--strategy-code",
            "STR001",
            "--trade-time",
            "2026-06-16T09:30:00+08:00",
            "--price",
            "0",
            "--quantity",
            "2",
        ],
    )
    assert invalid_price.exit_code != 0
    assert "price" in invalid_price.output
    assert "大于 0" in invalid_price.output

    zero_quantity = runner.invoke(
        cli,
        [
            "trade",
            "create",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_AGENT_001",
            "--instrument-code",
            "T2606",
            "--account-code",
            "ACC001",
            "--strategy-code",
            "STR001",
            "--trade-time",
            "2026-06-16T09:30:00+08:00",
            "--price",
            "101.25",
            "--quantity",
            "0",
        ],
    )
    assert zero_quantity.exit_code != 0
    assert "quantity" in zero_quantity.output
    assert "买入用正数" in zero_quantity.output

    naive_time = runner.invoke(
        cli,
        [
            "trade",
            "create",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_AGENT_001",
            "--instrument-code",
            "T2606",
            "--account-code",
            "ACC001",
            "--strategy-code",
            "STR001",
            "--trade-time",
            "2026-06-16T09:30:00",
            "--price",
            "101.25",
            "--quantity",
            "2",
        ],
    )
    assert naive_time.exit_code != 0
    assert "trade_time" in naive_time.output
    assert "2026-06-16T09:30:00+08:00" in naive_time.output


def test_trade_update_adds_advice_to_backend_errors(monkeypatch, tmp_path: Path) -> None:
    """trade update should preserve backend errors and append correction advice."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_patch(self, path, json_body=None, params=None):  # noqa: ANN001
        raise CliApiError(
            "Only same-day futures trades can be modified",
            status_code=400,
            payload={"error": {"message": "Only same-day futures trades can be modified"}},
        )

    monkeypatch.setattr("agent_rms.api_client.ApiClient.patch", fake_patch)

    result = runner.invoke(
        cli,
        [
            "trade",
            "update",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_HIST",
            "--instrument-code",
            "T2606",
            "--account-code",
            "ACC001",
            "--strategy-code",
            "STR001",
            "--trade-time",
            "2026-06-16T13:15:00+08:00",
            "--price",
            "102.75",
            "--quantity",
            "3",
        ],
    )

    assert result.exit_code != 0
    assert "Only same-day futures trades can be modified" in result.output
    assert "查询当日成交" in result.output


def test_trade_delete_adds_advice_to_settled_trade_errors(monkeypatch, tmp_path: Path) -> None:
    """trade delete should explain settled-trade backend rejections."""
    runner = CliRunner()
    _save_default_store(tmp_path, monkeypatch)

    def fake_delete(self, path, params=None):  # noqa: ANN001
        raise CliApiError(
            "Settled futures trades cannot be modified",
            status_code=400,
            payload={"error": {"message": "Settled futures trades cannot be modified"}},
        )

    monkeypatch.setattr("agent_rms.api_client.ApiClient.delete", fake_delete)

    result = runner.invoke(
        cli,
        [
            "trade",
            "delete",
            "--product-code",
            "PROD001",
            "--trade-code",
            "FUT_SETTLED",
            "--yes",
        ],
    )

    assert result.exit_code != 0
    assert "Settled futures trades cannot be modified" in result.output
    assert "调整流程" in result.output

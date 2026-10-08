"""Sovereign mode keeps model calls and telemetry off OpenSRE-hosted services."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from config.account import account_llm_route, agent_bearer_token, resolve_account_token
from config.constants.account import OPENSRE_ACCOUNT_METADATA_PATH_ENV, OPENSRE_ACCOUNT_TOKEN_ENV
from config.constants.billing import USAGE_SECRET_ENV, WEBAPP_URL_ENV
from config.constants.sovereign import SOVEREIGN_MODE_ENV
from surfaces.cli.commands.account import account_command
from surfaces.interactive_shell.runtime.startup import account_gate


@pytest.fixture(autouse=True)
def _signed_in_gateway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A process that would take the hosted route if sovereign mode were off."""
    monkeypatch.setenv(OPENSRE_ACCOUNT_METADATA_PATH_ENV, str(tmp_path / "account.json"))
    monkeypatch.setenv(OPENSRE_ACCOUNT_TOKEN_ENV, "osre_gw_org_A.signature")
    monkeypatch.setenv(WEBAPP_URL_ENV, "https://app.example")
    monkeypatch.setenv(USAGE_SECRET_ENV, "fleet-secret")
    monkeypatch.setenv(SOVEREIGN_MODE_ENV, "1")


def test_sovereign_mode_drops_the_hosted_llm_route_and_account_bearers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert account_llm_route() is None
    assert resolve_account_token() == ""
    assert agent_bearer_token() == ""

    monkeypatch.delenv(SOVEREIGN_MODE_ENV)
    assert account_llm_route() is not None


def test_sovereign_mode_skips_the_shell_sign_in_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_gate, "is_test_run", lambda: False)

    def _no_webapp_call() -> None:
        raise AssertionError("sovereign mode must not ask the webapp for account status")

    monkeypatch.setattr(account_gate, "current_account_status", _no_webapp_call)

    assert account_gate.pass_sign_in_gate(console=None) is True  # type: ignore[arg-type]


def test_sovereign_mode_refuses_account_login() -> None:
    result = CliRunner().invoke(account_command, ["login"], obj={"json": False})

    assert result.exit_code != 0
    assert SOVEREIGN_MODE_ENV in result.output

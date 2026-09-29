"""GitHub failures that need the user to grant access carry the page to fix them."""

from __future__ import annotations

import io
from email.message import Message
from pathlib import Path
from urllib import error

import pytest

from integrations.github.access import (
    GITHUB_PERMISSIONS_ACTION,
    classify_github_access_failure,
    github_oauth_app_permissions_url,
)
from integrations.github.client import _http_error
from integrations.github.envelope import normalize_github_tool_result
from integrations.store import upsert_integration


@pytest.fixture(autouse=True)
def _no_webapp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import integrations.store as store

    monkeypatch.setattr(store, "STORE_PATH", tmp_path / "integrations.json")
    monkeypatch.delenv("OPENSRE_WEBAPP_URL", raising=False)
    monkeypatch.setenv("OPENSRE_GITHUB_OAUTH_CLIENT_ID", "Iv-test-client")


def _headers(**values: str) -> Message:
    message = Message()
    for key, value in values.items():
        message[key.replace("_", "-")] = value
    return message


def test_org_that_restricts_oauth_apps_points_at_the_grant_page() -> None:
    issue = classify_github_access_failure(
        status_code=403,
        message="Although you appear to have the correct authorization credentials, the "
        "`acme` organization has enabled OAuth App access restrictions",
        path="/repos/acme/api",
        token="gho_abc",
    )

    assert issue is not None
    assert issue.kind == "organization_approval"
    assert issue.permissions_url == (
        "https://github.com/settings/connections/applications/Iv-test-client"
    )
    assert issue.permissions_url in issue.user_action
    assert "acme" in issue.user_action


def test_saml_enforcement_uses_the_sso_url_github_sends() -> None:
    sso_url = "https://github.com/orgs/acme/sso?authorization_request=XYZ"
    issue = classify_github_access_failure(
        status_code=403,
        message="Resource protected by organization SAML enforcement.",
        headers=_headers(X_GitHub_SSO=f"required; url={sso_url}"),
        path="/repos/acme/api/pulls",
    )

    assert issue is not None
    assert issue.kind == "sso_authorization"
    assert issue.permissions_url == sso_url


def test_fine_grained_token_without_scope_header_is_not_a_missing_scope() -> None:
    # Fine-grained PATs never send X-OAuth-Scopes; treating the absent header as
    # "no scopes" would tell the user to reconnect instead of widening repo access.
    issue = classify_github_access_failure(
        status_code=403,
        message="Resource not accessible by personal access token",
        headers=_headers(X_Accepted_OAuth_Scopes="repo"),
        path="/repos/acme/api/actions/runs",
        token="github_pat_abc",
    )

    assert issue is not None
    assert issue.kind == "repository_access"
    assert issue.permissions_url == "https://github.com/settings/personal-access-tokens"


def test_oauth_token_lacking_the_accepted_scope_asks_to_reconnect() -> None:
    issue = classify_github_access_failure(
        status_code=403,
        message="Must have admin rights to Repository.",
        headers=_headers(X_Accepted_OAuth_Scopes="workflow", X_OAuth_Scopes="repo, read:org"),
        path="/repos/acme/api/actions/workflows",
        token="gho_abc",
    )

    assert issue is not None
    assert issue.kind == "missing_scopes"
    assert "workflow" in issue.user_action
    assert "/integrations setup github" in issue.user_action


def test_rest_error_text_carries_the_fix_to_every_tool() -> None:
    http_error = error.HTTPError(
        "https://api.github.com/repos/acme/private",
        404,
        "Not Found",
        _headers(),
        io.BytesIO(b""),
    )

    exc = _http_error(
        http_error, detail='{"message":"Not Found"}', path="/repos/acme/private", token="gho_x"
    )

    assert exc.access is not None
    assert exc.access.kind == "repository_access"
    assert github_oauth_app_permissions_url() in str(exc)


def test_mcp_failure_payload_tells_the_agent_to_ask_the_user() -> None:
    payload = normalize_github_tool_result(
        {
            "is_error": True,
            "text": "failed to get repository: GET https://api.github.com/repos/acme/api: "
            "401 Bad credentials []",
            "tool": "get_repository",
            "arguments": {},
        }
    )

    assert payload["available"] is False
    assert payload["action_required"] == GITHUB_PERMISSIONS_ACTION
    assert payload["access_issue"] == "reauthorize"
    assert "reconnect" in payload["user_action"].lower()


def test_missing_file_is_not_reported_as_missing_access() -> None:
    assert (
        classify_github_access_failure(
            status_code=404, message="Not Found", path="/repos/acme/api/contents/docs/x.md"
        )
        is None
    )


def test_workspace_permissions_page_is_the_one_the_agent_opens() -> None:
    page = "https://github.com/settings/connections/applications/from-workspace"
    upsert_integration(
        "github",
        {
            "instances": [
                {
                    "name": "default",
                    "tags": {"auth_source": "opensre_account", "permissions_url": page},
                    "credentials": {"auth_token": "gho_workspace"},
                }
            ]
        },
    )

    issue = classify_github_access_failure(
        status_code=403,
        message="OAuth App access restrictions",
        path="/repos/acme/api",
        token="gho_workspace",
    )

    assert issue is not None
    assert issue.permissions_url == page


def test_unrelated_failure_is_left_alone() -> None:
    assert (
        classify_github_access_failure(
            status_code=502, message="Bad gateway", path="/repos/acme/api"
        )
        is None
    )

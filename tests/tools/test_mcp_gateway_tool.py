"""Tests for generic MCP gateway function tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import mcp_types as types

from core.tool import ERROR_KIND_REFUSED, SideEffectLevel
from integrations.mcp_gateway import (
    McpGatewayClient,
    McpGatewayConfig,
    McpGatewayRefused,
    validate_mcp_gateway_config,
)
from integrations.mcp_gateway.tools.gateway import (
    call_mcp_gateway_read_tool,
    call_mcp_gateway_tool,
    list_mcp_gateway_tools,
)
from tests.tools.conftest import BaseToolContract, mock_agent_state


class TestMcpGatewayListContract(BaseToolContract):
    def get_tool_under_test(self):
        return list_mcp_gateway_tools.__opensre_registered_tool__


class TestMcpGatewayReadContract(BaseToolContract):
    def get_tool_under_test(self):
        return call_mcp_gateway_read_tool.__opensre_registered_tool__


class TestMcpGatewayCallContract(BaseToolContract):
    def get_tool_under_test(self):
        return call_mcp_gateway_tool.__opensre_registered_tool__


def _sources(*, read_only_tools: tuple[str, ...] = ("status",)) -> dict[str, object]:
    return mock_agent_state(
        {
            "mcp_gateway": {
                "connection_verified": True,
                "source": "local env",
                "config": {
                    "url": "http://127.0.0.1:8765/mcp",
                    "auth_token": "secret",
                    "allowed_tools": ("status", "restart_service"),
                    "read_only_tools": read_only_tools,
                },
            }
        }
    )


def test_tool_contracts_encode_read_and_mutation_boundaries() -> None:
    listing = list_mcp_gateway_tools.__opensre_registered_tool__
    read = call_mcp_gateway_read_tool.__opensre_registered_tool__
    external = call_mcp_gateway_tool.__opensre_registered_tool__

    assert listing.side_effect_level is SideEffectLevel.READ_ONLY
    assert read.side_effect_level is SideEffectLevel.READ_ONLY
    assert read.requires_approval is False
    assert external.side_effect_level is SideEffectLevel.EXTERNAL
    assert external.requires_approval is True


def test_public_schemas_do_not_expose_connection_or_policy_values() -> None:
    for tool_fn in (
        list_mcp_gateway_tools,
        call_mcp_gateway_read_tool,
        call_mcp_gateway_tool,
    ):
        registered = tool_fn.__opensre_registered_tool__
        assert registered.injected_params == ("_mcp_gateway_client",)
        assert "_mcp_gateway_client" not in registered.public_input_schema.get("properties", {})


def test_read_tool_only_available_with_certified_read_only_names() -> None:
    registered = call_mcp_gateway_read_tool.__opensre_registered_tool__

    assert registered.is_available(_sources()) is True
    assert registered.is_available(_sources(read_only_tools=())) is False


def test_extract_params_injects_client_without_exposing_raw_secret() -> None:
    registered = call_mcp_gateway_tool.__opensre_registered_tool__

    params = registered.extract_params(_sources())

    assert set(params) == {"_mcp_gateway_client"}
    assert params["_mcp_gateway_client"].config.auth_token == "secret"


def test_list_labels_tools_by_access_policy() -> None:
    client = MagicMock()
    client.config.read_only_tools = ("status",)
    client.config.auth_token = ""
    client.list_tools.return_value = [
        {"name": "status", "description": "Status", "input_schema": {}},
        {"name": "restart_service", "description": "Restart", "input_schema": {}},
    ]

    result = list_mcp_gateway_tools(_mcp_gateway_client=client)

    assert result["available"] is True
    assert result["tools"] == [
        {"name": "status", "description": "Status", "access": "read_only"},
        {
            "name": "restart_service",
            "description": "Restart",
            "access": "approval_required",
        },
    ]


def test_read_tool_calls_client_in_read_only_mode() -> None:
    client = MagicMock()
    client.call_tool.return_value = {
        "is_error": False,
        "tool": "status",
        "arguments": {},
        "text": "ready",
        "structured_content": {"ok": True},
        "content": [],
    }

    result = call_mcp_gateway_read_tool("status", _mcp_gateway_client=client)

    client.call_tool.assert_called_once_with("status", {}, read_only=True)
    assert result["available"] is True
    assert result["text"] == "ready"


def test_external_tool_sanitizes_mcp_execution_errors() -> None:
    client = MagicMock()
    client.call_tool.return_value = {
        "is_error": True,
        "tool": "restart_service",
        "arguments": {"service": "api"},
        "text": "permission denied: Bearer super-secret",
        "structured_content": {"debug_token": "super-secret"},
        "content": [{"type": "text", "text": "Bearer super-secret"}],
    }

    result = call_mcp_gateway_tool(
        "restart_service",
        {"service": "api"},
        _mcp_gateway_client=client,
    )

    assert result["available"] is True
    assert result["error"] == "MCP gateway tool reported an execution error."
    assert result["error_kind"] == "remote_tool_error"
    assert result["structured_content"] is None
    assert result["content"] == []
    assert "super-secret" not in repr(result)


def test_local_policy_refusal_stays_available() -> None:
    client = MagicMock()
    client.call_tool.side_effect = McpGatewayRefused("not allowed")

    result = call_mcp_gateway_tool("restart_service", _mcp_gateway_client=client)

    assert result["available"] is True
    assert result["error"] == "not allowed"
    assert result["error_kind"] == ERROR_KIND_REFUSED


def test_discovery_redaction_preserves_original_policy_names() -> None:
    config = McpGatewayConfig(
        url="https://mcp.example.test/mcp",
        auth_token="status",
        allowed_tools=("service_status",),
        read_only_tools=("service_status",),
    )
    with (
        patch(
            "integrations.mcp_gateway.client.list_mcp_tools",
            return_value=[
                types.Tool(
                    name="service_status",
                    description="Echo status",
                    input_schema={"description": "status"},
                )
            ],
        ),
        patch("integrations.mcp_gateway.client.call_mcp_tool", return_value={}) as call,
    ):
        client = McpGatewayClient(config)
        assert client.list_tools()[0]["name"] == "service_status"
        validation = validate_mcp_gateway_config(config)
        assert validation.ok
        assert "status" not in repr(validation.tool_names)
        client.call_tool("service_status", read_only=True)
        assert call.call_args.args[1] == "service_status"
        listing = list_mcp_gateway_tools(include_schema=True, _mcp_gateway_client=client)
        alias = listing["tools"][0]["name"]
        assert alias != "service_status" and "status" not in alias
        client.call_tool(alias, read_only=True)
        assert call.call_args.args[1] == "service_status"
    assert "status" not in repr(listing)
    assert listing["tools"] == [
        {
            "name": alias,
            "description": "Echo [redacted]",
            "schema_omitted": "Schema omitted because credential redaction would alter its contract.",
            "access": "read_only",
        }
    ]


def test_discovery_omits_oversized_schemas_and_preserves_other_contracts() -> None:
    import json

    client = MagicMock()
    client.config.auth_token = "secret-token"
    client.config.read_only_tools = ()
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    client.list_tools.return_value = [
        {"name": "huge", "description": "", "input_schema": {"description": "x" * 2000000}},
        *[
            {"name": f"tool_{i}", "description": "", "input_schema": {"description": "x" * 7000}}
            for i in range(8)
        ],
        {"name": "query", "description": "", "input_schema": schema},
    ]
    result = list_mcp_gateway_tools(include_schema=True, _mcp_gateway_client=client)
    assert len(json.dumps(result)) < 64000
    assert "input_schema" not in result["tools"][0]
    assert "size limit" in result["tools"][0]["schema_omitted"]
    assert any("budget" in item.get("schema_omitted", "") for item in result["tools"])
    assert result["tools"][-1]["input_schema"] == schema


def test_discovery_withholds_credentials_in_required_fields_without_rewriting_them() -> None:
    client = MagicMock()
    client.config.auth_token = "status"
    client.config.read_only_tools = ()
    schema = {
        "type": "object",
        "properties": {"status_code": {"type": "integer"}},
        "required": ["status_code"],
    }
    client.list_tools.return_value = [{"name": "check", "description": "", "input_schema": schema}]
    result = list_mcp_gateway_tools(include_schema=True, _mcp_gateway_client=client)
    item = result["tools"][0]
    assert "input_schema" not in item
    assert "redaction" in item["schema_omitted"]
    assert "status" not in repr(result)
    assert schema["required"] == ["status_code"]

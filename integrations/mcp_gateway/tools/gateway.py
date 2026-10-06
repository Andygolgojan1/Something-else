"""Discovery and execution tools for the configured MCP gateway."""

from __future__ import annotations

from typing import Any

from core.domain.types.tools import ToolSurface
from core.tool import ERROR_KIND_REFUSED, SideEffectLevel, report_run_error
from core.tool_framework import tool
from core.tool_framework.utils import build_mcp_tool_listing, unavailable_response
from integrations.mcp_gateway.client import McpGatewayClient
from integrations.mcp_gateway.config import build_mcp_gateway_config
from integrations.mcp_gateway.errors import (
    McpGatewayRefused,
    McpGatewayRequestError,
)
from integrations.mcp_gateway.redaction import public_tool_name, scrub_configured_token

_COMPONENT = "integrations.mcp_gateway.tools.gateway"
_INJECTED_PARAMS = ("_mcp_gateway_client",)
_REMOTE_TOOL_ERROR = "remote_tool_error"


def _source(sources: dict[str, dict]) -> dict[str, object]:
    raw = sources.get("mcp_gateway", {})
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("config")
    if not isinstance(nested, dict):
        return dict(raw)
    config = dict(nested)
    if "connection_verified" in raw:
        config["connection_verified"] = bool(raw["connection_verified"])
    return config


def _available(sources: dict[str, dict]) -> bool:
    return bool(_source(sources).get("connection_verified"))


def _read_tool_available(sources: dict[str, dict]) -> bool:
    raw = _source(sources)
    return bool(raw.get("connection_verified") and raw.get("read_only_tools"))


def _extract_client(sources: dict[str, dict]) -> dict[str, object]:
    raw = _source(sources)
    if not raw:
        return {}
    return {"_mcp_gateway_client": McpGatewayClient(build_mcp_gateway_config(raw))}


def _unavailable(
    error: str,
    *,
    tool_name: str | None = None,
    arguments: dict[str, object] | None = None,
) -> dict[str, object]:
    return unavailable_response(
        "mcp_gateway",
        error,
        tool_name=tool_name,
        arguments=arguments,
    )


def _refused(
    error: str,
    *,
    tool_name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    return {
        "source": "mcp_gateway",
        "available": True,
        "tool": tool_name,
        "arguments": arguments,
        "error": error,
        "error_kind": ERROR_KIND_REFUSED,
        "text": error,
        "structured_content": None,
        "content": [],
    }


def _remote_failure(
    error: str,
    *,
    tool_name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    return {
        "source": "mcp_gateway",
        "available": True,
        "tool": tool_name,
        "arguments": arguments,
        "error": error,
        "error_kind": _REMOTE_TOOL_ERROR,
        "text": error,
        "structured_content": None,
        "content": [],
    }


def _normalize_result(result: dict[str, object]) -> dict[str, object]:
    tool_name = str(result.get("tool") or "")
    arguments = result.get("arguments")
    normalized_arguments = arguments if isinstance(arguments, dict) else {}
    if result.get("is_error"):
        error = "MCP gateway tool reported an execution error."
        return _remote_failure(error, tool_name=tool_name, arguments=normalized_arguments)
    return {
        "source": "mcp_gateway",
        "available": True,
        "tool": tool_name,
        "arguments": normalized_arguments,
        "text": result.get("text", ""),
        "structured_content": result.get("structured_content"),
        "content": result.get("content", []),
    }


def _call(
    tool_name: str,
    arguments: dict[str, object] | None,
    *,
    client: McpGatewayClient | None,
    read_only: bool,
    registered_tool_name: str,
) -> dict[str, object]:
    normalized_arguments = arguments or {}
    if client is None:
        return _unavailable(
            "MCP gateway integration is not configured.",
            tool_name=tool_name,
            arguments=normalized_arguments,
        )
    try:
        result = client.call_tool(tool_name, normalized_arguments, read_only=read_only)
    except McpGatewayRefused as exc:
        return _refused(str(exc), tool_name=tool_name, arguments=normalized_arguments)
    except McpGatewayRequestError as exc:
        report_run_error(
            exc,
            tool_name=registered_tool_name,
            source="mcp_gateway",
            component=_COMPONENT,
            method="call_tool",
        )
        return _unavailable(str(exc), tool_name=tool_name, arguments=normalized_arguments)
    except Exception as exc:
        report_run_error(
            exc,
            tool_name=registered_tool_name,
            source="mcp_gateway",
            component=_COMPONENT,
            method="call_tool",
        )
        return _unavailable(
            f"MCP gateway request failed: {type(exc).__name__}.",
            tool_name=tool_name,
            arguments=normalized_arguments,
        )
    return _normalize_result(result)


@tool(
    name="list_mcp_gateway_tools",
    source="mcp_gateway",
    description=(
        "List tools exposed by the configured MCP gateway and show whether each is "
        "certified read-only or requires approval."
    ),
    use_cases=["Discovering allowed MCP gateway tools and their input schemas"],
    surfaces=(ToolSurface.CHAT,),
    side_effect_level=SideEffectLevel.READ_ONLY,
    input_schema={
        "type": "object",
        "properties": {
            "name_filter": {"type": "string"},
            "include_schema": {"type": "boolean"},
            "_mcp_gateway_client": {},
        },
        "required": [],
    },
    injected_params=_INJECTED_PARAMS,
    is_available=_available,
    extract_params=_extract_client,
)
def list_mcp_gateway_tools(
    name_filter: str | None = None,
    include_schema: bool = False,
    _mcp_gateway_client: McpGatewayClient | None = None,
    **_kwargs: Any,
) -> dict[str, object]:
    """Return a bounded list of allowed server tools and their access policy."""
    if _mcp_gateway_client is None:
        payload = _unavailable("MCP gateway integration is not configured.")
        payload["tools"] = []
        return payload
    try:
        descriptors = _mcp_gateway_client.list_tools()
    except McpGatewayRequestError as exc:
        report_run_error(
            exc,
            tool_name="list_mcp_gateway_tools",
            source="mcp_gateway",
            component=_COMPONENT,
            method="list_tools",
        )
        payload = _unavailable(str(exc))
        payload["tools"] = []
        return payload

    visible_descriptors: list[dict[str, object]] = []
    for descriptor in descriptors:
        visible_descriptors.append(
            {
                "name": public_tool_name(descriptor["name"], _mcp_gateway_client.config.auth_token),
                "description": scrub_configured_token(
                    descriptor["description"], _mcp_gateway_client.config.auth_token
                ),
                "input_schema": scrub_configured_token(
                    descriptor["input_schema"], _mcp_gateway_client.config.auth_token
                ),
            }
        )
    listing = build_mcp_tool_listing(
        visible_descriptors,
        name_filter=(name_filter or "").strip() or None,
        include_schema=bool(include_schema),
        filter_example="status restart",
    )
    read_only_names = {
        public_tool_name(name, _mcp_gateway_client.config.auth_token)
        for name in _mcp_gateway_client.config.read_only_tools
    }
    tools = listing.get("tools")
    if isinstance(tools, list):
        for item in tools:
            if isinstance(item, dict):
                item["access"] = (
                    "read_only" if item.get("name") in read_only_names else "approval_required"
                )
    return {"source": "mcp_gateway", "available": True, **listing}


_CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_name": {"type": "string"},
        "arguments": {"type": "object", "additionalProperties": True},
        "_mcp_gateway_client": {},
    },
    "required": ["tool_name"],
}


@tool(
    name="call_mcp_gateway_read_tool",
    source="mcp_gateway",
    description=(
        "Call a named MCP gateway tool that the operator explicitly certified as read-only."
    ),
    use_cases=["Reading status or evidence from an operator-certified MCP tool"],
    surfaces=(ToolSurface.CHAT,),
    side_effect_level=SideEffectLevel.READ_ONLY,
    input_schema=_CALL_SCHEMA,
    injected_params=_INJECTED_PARAMS,
    is_available=_read_tool_available,
    extract_params=_extract_client,
)
def call_mcp_gateway_read_tool(
    tool_name: str,
    arguments: dict[str, object] | None = None,
    _mcp_gateway_client: McpGatewayClient | None = None,
    **_kwargs: Any,
) -> dict[str, object]:
    """Call an MCP tool only when its exact name is certified read-only."""
    return _call(
        tool_name,
        arguments,
        client=_mcp_gateway_client,
        read_only=True,
        registered_tool_name="call_mcp_gateway_read_tool",
    )


@tool(
    name="call_mcp_gateway_tool",
    source="mcp_gateway",
    description=(
        "Call any allowed MCP gateway tool. This path may mutate external systems and "
        "therefore requires approval."
    ),
    use_cases=["Running an allowed MCP action after explicit approval"],
    surfaces=(ToolSurface.CHAT,),
    side_effect_level=SideEffectLevel.EXTERNAL,
    requires_approval=True,
    approval_reason="The selected MCP gateway tool may mutate an external system.",
    input_schema=_CALL_SCHEMA,
    injected_params=_INJECTED_PARAMS,
    is_available=_available,
    extract_params=_extract_client,
)
def call_mcp_gateway_tool(
    tool_name: str,
    arguments: dict[str, object] | None = None,
    _mcp_gateway_client: McpGatewayClient | None = None,
    **_kwargs: Any,
) -> dict[str, object]:
    """Call an allowed MCP tool through the approval-gated execution path."""
    return _call(
        tool_name,
        arguments,
        client=_mcp_gateway_client,
        read_only=False,
        registered_tool_name="call_mcp_gateway_tool",
    )


__all__ = [
    "call_mcp_gateway_read_tool",
    "call_mcp_gateway_tool",
    "list_mcp_gateway_tools",
]

"""Least-privilege client for a configured MCP gateway."""

from __future__ import annotations

from typing import TypedDict, cast

from integrations.mcp_client import McpSessionOptions, call_mcp_tool, list_mcp_tools
from integrations.mcp_gateway.config import McpGatewayConfig
from integrations.mcp_gateway.errors import McpGatewayRefused, safe_request_error


class McpGatewayToolDescriptor(TypedDict):
    """A tool advertised by the configured MCP server."""

    name: str
    description: str
    input_schema: object | None


class McpGatewayClient:
    """List and call tools while enforcing the configured exact-name allowlist."""

    def __init__(self, config: McpGatewayConfig) -> None:
        self.config = config

    def _session_options(self) -> McpSessionOptions:
        return {
            "session_url": self.config.url,
            "stdio_env": {},
            "integration_name": "MCP gateway",
            "config_env_name": "MCP_GATEWAY",
            "streamable_url_hint": "http://127.0.0.1:8765/mcp",
        }

    def list_all_tools(self) -> list[McpGatewayToolDescriptor]:
        try:
            tools = list_mcp_tools(
                self.config,
                timeout_entire_operation=True,
                **self._session_options(),
            )
        except Exception as exc:
            error = safe_request_error(exc, auth_token=self.config.auth_token)
        else:
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ]
        raise error

    def list_tools(self) -> list[McpGatewayToolDescriptor]:
        """List server tools after applying the optional overall allowlist."""
        tools = self.list_all_tools()
        if not self.config.allowed_tools:
            return tools
        allowed = set(self.config.allowed_tools)
        return [tool for tool in tools if tool["name"] in allowed]

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object] | None = None,
        *,
        read_only: bool = False,
    ) -> dict[str, object]:
        """Call one advertised tool after enforcing local execution policy."""
        name = tool_name.strip()
        if not name:
            raise McpGatewayRefused("MCP gateway tool_name is required.")
        if self.config.allowed_tools and name not in self.config.allowed_tools:
            raise McpGatewayRefused(f"MCP gateway tool '{name}' is not allowed.")
        if read_only and name not in self.config.read_only_tools:
            raise McpGatewayRefused(f"MCP gateway tool '{name}' is not certified read-only.")

        advertised_names = {tool["name"] for tool in self.list_tools()}
        if name not in advertised_names:
            raise McpGatewayRefused(f"MCP gateway tool '{name}' is not advertised by the server.")

        try:
            return cast(
                dict[str, object],
                call_mcp_tool(
                    self.config,
                    name,
                    arguments,
                    timeout_call=False,
                    timeout_entire_operation=True,
                    **self._session_options(),
                ),
            )
        except Exception as exc:
            error = safe_request_error(exc, auth_token=self.config.auth_token)
        raise error

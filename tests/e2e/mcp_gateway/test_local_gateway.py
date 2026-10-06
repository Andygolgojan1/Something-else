"""Opt-in end-to-end validation against the local sample MCP server.

Run with::

    OPENSRE_LIVE_MCP_GATEWAY=1 uv run pytest tests/e2e/mcp_gateway/test_local_gateway.py -q
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from integrations.mcp_gateway import McpGatewayClient, McpGatewayConfig, McpGatewayRequestError

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("OPENSRE_LIVE_MCP_GATEWAY") != "1",
        reason="Set OPENSRE_LIVE_MCP_GATEWAY=1 to run the local MCP gateway e2e test",
    ),
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_SERVER = _REPO_ROOT / "examples" / "mcp_gateway_server.py"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_port(port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    pytest.fail("Local sample MCP server did not start within 10 seconds")


@pytest.mark.parametrize("auth_token", ["", "sample-token"])
def test_local_streamable_http_gateway_lists_and_calls_both_policy_paths(auth_token: str) -> None:
    port = _free_port()
    command = [sys.executable, str(_SAMPLE_SERVER), "--port", str(port)]
    if auth_token:
        command.extend(("--auth-token", auth_token))
    process = subprocess.Popen(
        command,
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        client = McpGatewayClient(
            McpGatewayConfig(
                url=f"http://127.0.0.1:{port}/mcp",
                auth_token=auth_token,
                allowed_tools=("service_status", "restart_service"),
                read_only_tools=("service_status",),
            )
        )

        assert [tool["name"] for tool in client.list_tools()] == [
            "service_status",
            "restart_service",
        ]
        status = client.call_tool("service_status", {"service": "api"}, read_only=True)
        restart = client.call_tool("restart_service", {"service": "api"})

        assert status["structured_content"] == {
            "service": "api",
            "status": "healthy",
            "restart_requests": 0,
        }
        assert restart["structured_content"] == {
            "service": "api",
            "accepted": True,
            "restart_requests": 1,
        }
        if auth_token:
            unauthenticated = McpGatewayClient(
                McpGatewayConfig(
                    url=f"http://127.0.0.1:{port}/mcp",
                    auth_token="wrong-secret",
                )
            )
            with pytest.raises(McpGatewayRequestError) as failure:
                unauthenticated.list_all_tools()
            assert "MCP_GATEWAY_AUTH_TOKEN" in str(failure.value)
            assert "wrong-secret" not in str(failure.value)
            assert "sample-challenge-secret" not in str(failure.value)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

"""Approval prompts must never render raw secrets into multi-member chats."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.llm.types import ToolCall
from core.tool import ToolExecutionRequest
from gateway.core.middleware.approvals import (
    ARGS_PREVIEW_LIMIT,
    approval_tool_hooks,
    arguments_preview,
)
from integrations.mcp_gateway.tools.gateway import call_mcp_gateway_tool


def test_arguments_preview_redacts_sensitive_keys() -> None:
    preview = arguments_preview(
        {
            "channel": "ops",
            "api_key": "sk-live-super-secret",
            "token": "xoxb-should-not-leak",
            "password": "hunter2",
            "message": "restart checkout",
        }
    )

    assert "sk-live-super-secret" not in preview
    assert "xoxb-should-not-leak" not in preview
    assert "hunter2" not in preview
    assert "restart checkout" in preview
    assert "[redacted]" in preview.lower() or "REDACTED" in preview


def test_arguments_preview_scrubs_bearer_tokens_under_neutral_keys() -> None:
    preview = arguments_preview(
        {"headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz012345"}}
    )

    assert "abcdefghijklmnopqrstuvwxyz012345" not in preview
    assert "Bearer" in preview or "REDACTED" in preview or "redacted" in preview


def test_chat_preview_retains_later_nested_mutation_targets() -> None:
    arguments = {
        "tool_name": "restart_service",
        "arguments": {"padding": "x" * 10000, "service": "prod", "message": "Bearer sample-token"},
    }
    preview = arguments_preview(arguments)
    assert len(preview) <= ARGS_PREVIEW_LIMIT
    assert '"service": "prod"' in preview
    assert "sample-token" not in preview
    assert "[truncated]" in preview
    assert arguments["arguments"]["padding"] == "x" * 10000


def test_chat_hook_never_approves_arguments_with_hidden_fields() -> None:
    arguments = {"arguments": {f"field_{i}": i for i in range(100)}}
    prompter = MagicMock()
    prompter.request.return_value = (True, "operator")
    hook = approval_tool_hooks(prompter).before_tool_call
    assert hook is not None
    decision = hook(
        ToolExecutionRequest(
            tool_call=ToolCall(id="call-1", name="call_mcp_gateway_tool", input=arguments),
            tool=call_mcp_gateway_tool.__opensre_registered_tool__,
            arguments=arguments,
            source="test",
            resolved_integrations={},
        )
    )
    assert decision is not None and decision.blocked and not decision.approved
    prompter.request.assert_not_called()

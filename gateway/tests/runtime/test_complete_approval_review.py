"""Approval controls cannot precede complete, successfully delivered evidence."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.llm.types import ToolCall
from core.tool import ToolExecutionRequest
from gateway.core.middleware.approvals import ApprovalBroker, approval_arguments_preview
from gateway.core.prompt_intake.worker import _Approvals
from gateway.transports.buzz.approvals import BuzzApprovalPrompter
from gateway.transports.buzz.pending_approvals import PendingApprovals
from gateway.transports.discord import approvals as discord_approvals
from gateway.transports.slack.delivery.approvals import ThreadApprovalPrompter
from gateway.transports.telegram.approvals import TelegramApprovalPrompter
from integrations.mcp_gateway.tools.gateway import call_mcp_gateway_tool


def _arguments() -> dict:
    return {
        "arguments": {
            "query": "x" * 5000 + "DROP TABLE production;" + "x" * 5000,
            "api_key": "must-never-leak",
        }
    }


@pytest.mark.parametrize("platform", ["slack", "telegram", "discord", "buzz"])
@pytest.mark.parametrize("delivery_fails", [False, True])
def test_complete_pages_arrive_before_controls_or_no_approval(
    platform: str,
    delivery_fails: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _arguments()
    preview = approval_arguments_preview(arguments)
    assert "DROP TABLE" not in preview.text
    posted: list[str] = []
    controls: list[str] = []
    client = MagicMock()
    broker = ApprovalBroker()

    def deliver(text: str, has_controls: bool) -> bool:
        if has_controls:
            controls.append(text)
            review_id = posted[0].split("arguments ", 1)[1].split(" ", 1)[0]
            assert review_id in text
            assert all(review_id in page.split("\n", 1)[0] for page in posted)
            complete = "".join(page.split("```\n", 1)[1].rsplit("\n```", 1)[0] for page in posted)
            assert json.loads(complete) == json.loads(preview.full_text)
            assert "DROP TABLE production;" in complete
            assert "must-never-leak" not in complete
        else:
            assert len(text) < 2000
            posted.append(text)
        return not delivery_fails

    def slack_post(**kwargs):
        ok = deliver(kwargs["text"], any(b["type"] == "actions" for b in kwargs["blocks"]))
        return "message-1" if ok else None

    def telegram_post(_chat, text, **kwargs):
        ok = deliver(text, bool(kwargs.get("reply_markup")))
        return (True, "", "message-1") if ok else (False, "failure", "")

    def discord_post(**kwargs):
        ok = deliver(kwargs["content"], bool(kwargs.get("components")))
        return "message-1" if ok else None

    def buzz_post(**kwargs):
        ok = deliver(kwargs["content"], "reply **approve**" in kwargs["content"])
        return {"success": ok, "error": "", "event_id": "message-1"}

    if platform == "slack":
        client.post_message.side_effect = slack_post
        prompter = ThreadApprovalPrompter(
            client=client, broker=broker, channel_id="C1", thread_ts="T1"
        )
    elif platform == "telegram":
        client.send_message.side_effect = telegram_post
        prompter = TelegramApprovalPrompter(client=client, broker=broker, chat_id="C1")
    elif platform == "discord":
        monkeypatch.setattr(discord_approvals, "send_message", discord_post)
        monkeypatch.setattr(discord_approvals, "send_message_with_components", discord_post)
        monkeypatch.setattr(discord_approvals, "edit_message", lambda **_kw: True)
        prompter = discord_approvals.DiscordApprovalPrompter(
            broker=broker, bot_token="bot", channel_id="C1"
        )
    else:
        client.send_message.side_effect = buzz_post
        client.edit_message.return_value = {"success": True, "error": ""}
        prompter = BuzzApprovalPrompter(
            broker=broker,
            client=client,
            channel_id="C1",
            requester_pubkey="operator",
            pending_approvals=PendingApprovals(),
        )

    def wait(_approval_id, *, timeout):
        assert timeout > 0
        assert controls and posted
        return (True, "operator")

    monkeypatch.setattr(broker, "wait", wait)
    result = prompter.request(
        tool_name="call_mcp_gateway_tool", reason="mutation", arguments=arguments, expiry_seconds=30
    )
    assert result[0] is not delivery_fails
    if delivery_fails:
        assert not controls
    broker.close()


def test_hosted_approval_question_contains_complete_redacted_arguments() -> None:
    arguments = _arguments()
    session = SimpleNamespace(pending_user_choice=None)
    request = ToolExecutionRequest(
        tool_call=ToolCall(id="call-1", name="call_mcp_gateway_tool", input=arguments),
        tool=call_mcp_gateway_tool.__opensre_registered_tool__,
        arguments=arguments,
        source="test",
        resolved_integrations={},
    )
    result = _Approvals(session, set()).before_tool_call(request)
    assert result is not None and result.blocked
    assert "DROP TABLE production;" in session.pending_user_choice.note
    assert "must-never-leak" not in session.pending_user_choice.note
    assert len(session.pending_user_choice.note) > 10000

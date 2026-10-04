"""Retain skill context through menu answers and clear it for new requests."""

from __future__ import annotations

from typing import Any

from core.agent_harness.session.capabilities import withheld_skill_capability
from core.agent_harness.session.pending_choice import parse_ask_user_answers


def prepare_active_skill(session: Any, message: str) -> None:
    """Leave slash commands and menu answers in their current skill.

    A skill this host cannot run (it needs a capability the host withholds) is
    dropped even on an answer, so a session saved before that rule existed does
    not keep driving it.
    """
    if not message.strip().startswith("/") and not parse_ask_user_answers(message):
        session.active_skill = None
    elif withheld_skill_capability(session, getattr(session, "active_skill", None)):
        session.active_skill = None

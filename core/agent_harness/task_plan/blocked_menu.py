"""Which menu may open once a plan step was newly blocked this turn.

A step blocked this turn is resolved with the user, so a model-issued
``ask_user_choice`` must then be about that step: its ``blocked_step``
argument names it. Menus the host opens itself (a skill's entry menu, a
gateway question parked on the shell) never pass through the tool hooks and
are never refused here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.agent_harness.session.pending_choice import question_key
from core.agent_harness.task_plan.evidence import blocked_this_turn

_BLOCKED_STEP_ARG = "blocked_step"
_ONE_STEP_REFUSAL = (
    "Plan step '{step}' was blocked this turn. Ask about that blocker now: call "
    "ask_user_choice with blocked_step='{step}', options a tool here can carry out, "
    "and one to leave it blocked."
)
_STEPS_REFUSAL = (
    "Plan steps {steps} were blocked this turn. Ask about one of those blockers now: "
    "call ask_user_choice with blocked_step set to that step's exact text, options a "
    "tool here can carry out, and one to leave it blocked."
)


def _quoted(steps: tuple[str, ...]) -> str:
    """``'a' and 'b'``, or ``'a', 'b' and 'c'``."""
    names = [f"'{step}'" for step in steps]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def blocked_step_menu_refusal(session: Any, arguments: Mapping[str, Any]) -> str | None:
    """Why this menu may not open now; None when it may.

    Any menu may open while no step was newly blocked this turn. Otherwise
    ``blocked_step`` must name one of those steps, ignoring case and spacing.
    """
    blocked = blocked_this_turn(session)
    if not blocked:
        return None
    named = question_key(str(arguments.get(_BLOCKED_STEP_ARG) or ""))
    if named and any(question_key(step) == named for step in blocked):
        return None
    if len(blocked) == 1:
        return _ONE_STEP_REFUSAL.format(step=blocked[0])
    return _STEPS_REFUSAL.format(steps=_quoted(blocked))


__all__ = ["blocked_step_menu_refusal"]

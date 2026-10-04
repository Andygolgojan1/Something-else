"""After a plan step is blocked, the only menu the model may open is one about that step.

Observed live: ``run_ci_repair_demo`` was refused, the step was marked blocked,
and the turn closed on the skill's success-path menu ("Hand off the next
failure?") instead of a question about the blocker.
"""

from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from config.constants.tooling import ToolBlockedBy
from core.agent_harness.task_plan.plan import PlanStepStatus
from core.agent_harness.tools.tool_context import ACTION_TOOL_CONTEXT_RESOURCE_KEY, ActionToolScope
from core.agent_harness.turns.plan_hooks import with_task_plan_hooks
from core.domain.types.tools import ToolRole
from core.llm.types import ToolCall
from core.tool.contracts import AgentTool, AgentToolContext, RuntimeTool
from core.tool.execution import ToolExecutionResult, execute_tool_calls
from surfaces.interactive_shell.session import Session
from tools.interactive_shell.actions.ask_choice import ask_user_choice_tool
from tools.interactive_shell.actions.update_plan import execute_update_plan_tool

_IP = PlanStepStatus.IN_PROGRESS
_P = PlanStepStatus.PENDING
_B = PlanStepStatus.BLOCKED
_STEPS = ("Seed the demo repository", "Run the repair", "Offer the next step")
_SUCCESS_MENU: dict[str, Any] = {
    "title": "Hand off the next failure?",
    "options": ["Fix one from Slack", "Not now"],
}
_WORK: tuple[str, dict[str, Any]] = ("run_ci_repair_demo", {})


class _Ports:
    def tty_interactive(self) -> bool:
        return True


class _Turn:
    """One action turn: the plan hooks over real ``update_plan`` and ``ask_user_choice``."""

    def __init__(self) -> None:
        message = "Run the CI repair demo"
        self.session = Session()
        self.hooks = with_task_plan_hooks(None, self.session, turn_user_message=message)
        self.scope = ActionToolScope(
            session=self.session,
            console=Console(file=io.StringIO()),
            slash_ports=_Ports(),
            turn_user_message=message,
        )

        def write_plan(args: dict[str, Any], _ctx: AgentToolContext) -> dict[str, Any]:
            return execute_update_plan_tool(args, self.scope)

        self.tools: list[RuntimeTool] = [
            AgentTool(
                name="update_plan",
                description="plan",
                input_schema={"type": "object", "additionalProperties": True},
                execute=write_plan,
                role=ToolRole.BOOKKEEPING,
            ),
            AgentTool(
                name="run_ci_repair_demo",
                description="repair",
                input_schema={"type": "object", "additionalProperties": True},
                execute=lambda _args, _ctx: {"ok": True},
            ),
            ask_user_choice_tool,
        ]

    def batch(self, *calls: tuple[str, dict[str, Any]]) -> list[ToolExecutionResult]:
        return execute_tool_calls(
            [ToolCall(id=f"c{i}", name=name, input=args) for i, (name, args) in enumerate(calls)],
            self.tools,
            {},
            hooks=self.hooks,
            tool_resources={ACTION_TOOL_CONTEXT_RESOURCE_KEY: self.scope},
        )

    def plan(self, *statuses: str) -> tuple[str, dict[str, Any]]:
        steps = [{"step": s, "status": st} for s, st in zip(_STEPS, statuses, strict=True)]
        return ("update_plan", {"plan": steps, "explanation": "The repair was refused."})

    def statuses(self) -> list[PlanStepStatus]:
        assert self.session.task_plan is not None
        return [item.status for item in self.session.task_plan.steps]


def _turn_that_blocked_the_repair() -> _Turn:
    """Step 1 is in progress and earned its completion; step 2 was blocked this turn."""
    turn = _Turn()
    turn.batch(turn.plan("in_progress", "pending", "pending"), _WORK)
    turn.batch(turn.plan("in_progress", "blocked", "pending"), _WORK)
    assert turn.statuses() == [_IP, _B, _P]
    return turn


def test_a_menu_that_is_not_about_the_blocked_step_is_refused_and_moves_nothing() -> None:
    turn = _turn_that_blocked_the_repair()

    # Act: the success-path menu, alone in its response, so the host advance is armed.
    [result] = turn.batch(("ask_user_choice", _SUCCESS_MENU))

    # Assert: refused with its own blocked_by, nothing queued, and the plan did not
    # move (the menu counts as step work, so an advance would complete step 1).
    assert result.is_error is True
    assert result.metadata[ToolBlockedBy.BLOCKED_STEP_MENU] is True
    assert "blocked_step='Run the repair'" in str(result.content)
    assert turn.session.pending_user_choice is None
    assert turn.statuses() == [_IP, _B, _P]


def test_a_menu_naming_the_blocked_step_opens_whatever_its_case_and_spacing() -> None:
    turn = _turn_that_blocked_the_repair()
    menu = {
        "title": "The repair was refused",
        "options": ["Retry after the gateway updates", "Leave it blocked"],
        "blocked_step": "  run THE   repair ",
    }

    # Act: the real tool's schema and signature accept the argument.
    [result] = turn.batch(("ask_user_choice", menu))

    # Assert
    assert result.is_error is False
    assert result.details["menu"] == "queued"
    assert turn.session.pending_user_choice is not None
    assert turn.session.pending_user_choice.title == "The repair was refused"


def test_with_no_step_blocked_this_turn_any_menu_opens() -> None:
    turn = _Turn()
    turn.batch(turn.plan("in_progress", "pending", "pending"), _WORK)

    [result] = turn.batch(("ask_user_choice", _SUCCESS_MENU))

    assert result.is_error is False
    assert turn.session.pending_user_choice is not None
    assert turn.session.pending_user_choice.title == _SUCCESS_MENU["title"]

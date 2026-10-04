"""Tool-execution wraps for task-plan evidence, the plan guards, and host advance.

Rules live in ``task_plan.evidence``, ``task_plan.required``,
``task_plan.blocked_menu`` and ``task_plan.advance``. This module records
returns, refuses the next work call when no plan is open, refuses a menu that
is not about a step blocked this turn, and moves the plan forward before the
first work call of a batch that carries no ``update_plan``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from config.constants.tooling import ToolBlockedBy
from core.agent_harness.task_plan.advance import auto_advance_task_plan
from core.agent_harness.task_plan.blocked_menu import blocked_step_menu_refusal
from core.agent_harness.task_plan.evidence import (
    UPDATE_PLAN_TOOL,
    is_plan_work_name,
    record_plan_evidence,
    reset_plan_evidence,
)
from core.agent_harness.task_plan.required import PLAN_REQUIRED_REASON, plan_required
from core.domain.types.tools import ToolRole
from core.llm.types import ToolCall
from core.tool.execution import (
    BeforeToolCallResult,
    ToolExecutionHooks,
    ToolExecutionPatch,
    ToolExecutionRequest,
    ToolExecutionResult,
    tool_role,
)

#: The model's menu; the blocked-step rule refuses no other call.
_ASK_USER_CHOICE_TOOL = "ask_user_choice"


def with_task_plan_hooks(
    base: ToolExecutionHooks | None,
    session: Any,
    *,
    turn_user_message: str = "",
    answer_continues: bool = False,
) -> ToolExecutionHooks:
    """Wrap ``base`` so plan evidence is recorded, the plan guards can refuse a call,
    and the plan advances when the next step's tool is called.

    Advancement is armed once per provider batch (``before_tool_batch``) and
    fires at the first work call the guards let through, so a refused call —
    a menu that is not about a step blocked this turn included — or a batch
    that never reaches execution moves nothing. A batch carrying
    ``update_plan`` is the model's own write and is never advanced.
    ``turn_user_message`` lets an Ask User answer earn the step it settles.
    ``answer_continues`` (computed once at turn start) says the turn answers
    the plan owner's question; without it only a plan written this turn moves.
    """
    reset_plan_evidence(session)
    base_before = base.before_tool_call if base is not None else None
    base_after = base.after_tool_call if base is not None else None
    base_update = base.on_tool_update if base is not None else None
    base_batch = base.before_tool_batch if base is not None else None
    advance_armed = False

    def before_batch(tool_calls: Sequence[ToolCall]) -> None:
        nonlocal advance_armed
        if base_batch is not None:
            base_batch(tool_calls)
        advance_armed = all(call.name.strip() != UPDATE_PLAN_TOOL for call in tool_calls)

    def before(request: ToolExecutionRequest) -> BeforeToolCallResult | None:
        nonlocal advance_armed
        decision = base_before(request) if base_before is not None else None
        if decision is not None and decision.blocked:
            return decision
        role = tool_role(request.tool)
        if plan_required(
            session,
            tool_name=request.tool_call.name,
            arguments=request.arguments,
            is_action=role is ToolRole.ACTION,
        ):
            return BeforeToolCallResult(
                blocked=True,
                reason=PLAN_REQUIRED_REASON,
                metadata={ToolBlockedBy.PLAN_REQUIRED: True},
            )
        # Before the advance: the menu counts as step work, so a refused one
        # must not move the plan.
        if request.tool_call.name == _ASK_USER_CHOICE_TOOL:
            refusal = blocked_step_menu_refusal(session, request.arguments)
            if refusal is not None:
                return BeforeToolCallResult(
                    blocked=True,
                    reason=refusal,
                    metadata={ToolBlockedBy.BLOCKED_STEP_MENU: True},
                )
        if (
            advance_armed
            and role is not ToolRole.BOOKKEEPING
            and is_plan_work_name(request.tool_call.name, request.arguments)
        ):
            advance_armed = False
            auto_advance_task_plan(
                session,
                turn_user_message=turn_user_message,
                answer_continues=answer_continues,
            )
        return decision

    def after(
        request: ToolExecutionRequest, result: ToolExecutionResult
    ) -> ToolExecutionPatch | None:
        patch = base_after(request, result) if base_after is not None else None
        record_plan_evidence(
            session,
            request.tool_call.name,
            request.arguments,
            is_error=result.is_error,
            details=result.details,
        )
        return patch

    return ToolExecutionHooks(
        before_tool_call=before,
        after_tool_call=after,
        on_tool_update=base_update,
        before_tool_batch=before_batch,
    )


__all__ = ["with_task_plan_hooks"]

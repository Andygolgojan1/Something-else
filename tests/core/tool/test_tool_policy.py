"""The read-only operator policy is a ceiling no host hook can lift."""

from __future__ import annotations

from typing import Any

import pytest

from config.constants.sovereign import TOOL_POLICY_ALLOW_ENV, TOOL_POLICY_ENV
from config.constants.tooling import ToolBlockedBy
from core.llm.types import ToolCall
from core.tool import RegisteredTool, SideEffectLevel
from core.tool.execution import (
    BeforeToolCallResult,
    ToolExecutionHooks,
    ToolExecutionRequest,
    execute_tool_calls,
)


def _echo(value: str = "") -> dict[str, Any]:
    return {"value": value}


def _registered(
    name: str,
    *,
    level: SideEffectLevel | None,
    requires_approval: bool = False,
) -> RegisteredTool:
    return RegisteredTool.from_function(
        _echo,
        name=name,
        description="policy test tool",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        source="agent",
        side_effect_level=level,
        requires_approval=requires_approval,
    )


def _run(tool: RegisteredTool, hooks: ToolExecutionHooks | None = None) -> Any:
    call = ToolCall(id=f"{tool.name}-1", name=tool.name, input={"value": "x"})
    return execute_tool_calls([call], [tool], {}, hooks=hooks)[0]


def _approve_everything(_request: ToolExecutionRequest) -> BeforeToolCallResult:
    return BeforeToolCallResult(approved=True)


@pytest.fixture(autouse=True)
def _read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOOL_POLICY_ENV, "read_only")
    monkeypatch.delenv(TOOL_POLICY_ALLOW_ENV, raising=False)


@pytest.mark.parametrize(
    ("level", "requires_approval"),
    [
        (SideEffectLevel.MUTATING, False),
        (SideEffectLevel.EXTERNAL, False),
        (None, False),
        (SideEffectLevel.READ_ONLY, True),
    ],
)
def test_read_only_policy_blocks_writes_undeclared_and_approval_tools(
    level: SideEffectLevel | None, requires_approval: bool
) -> None:
    tool = _registered("risky", level=level, requires_approval=requires_approval)

    result = _run(tool, ToolExecutionHooks(before_tool_call=_approve_everything))

    assert result.is_error is True
    assert result.metadata[ToolBlockedBy.TOOL_POLICY] is True
    assert "read-only tool policy" in str(result.content)


@pytest.mark.parametrize("level", [SideEffectLevel.NONE, SideEffectLevel.READ_ONLY])
def test_read_only_policy_runs_read_tools(level: SideEffectLevel) -> None:
    result = _run(_registered("reader", level=level))

    assert result.is_error is False


def test_allowlist_exempts_only_the_named_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOOL_POLICY_ALLOW_ENV, "notify, other")

    allowed = _run(_registered("notify", level=SideEffectLevel.EXTERNAL))
    blocked = _run(_registered("page", level=SideEffectLevel.EXTERNAL))

    assert allowed.is_error is False
    assert blocked.is_error is True


def test_policy_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOOL_POLICY_ENV)

    result = _run(_registered("writer", level=SideEffectLevel.MUTATING))

    assert result.is_error is False

"""Gateway workflows retain one repair identity through execution and later inspection."""

from pathlib import Path
from typing import Any

import pytest

from config.constants import OPENSRE_MEMORY_AUTOEXTRACT_DISABLED_ENV, OPENSRE_MEMORY_DIR_ENV
from tests.core.agent.orchestration.action_execution_test_harness import (
    no_tool_response,
    tool_response,
)
from tests.utils.skill_workflow import BINDING, SkillWorkflow, batch

_SKILL = "operating-github-ci-repairs"


@pytest.mark.parametrize("observe_only", [False, True])
def test_gateway_uses_the_selected_task_without_restarting_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, observe_only: bool
) -> None:
    monkeypatch.setenv(OPENSRE_MEMORY_AUTOEXTRACT_DISABLED_ENV, "1")
    monkeypatch.setenv(OPENSRE_MEMORY_DIR_ENV, str(tmp_path / "memory"))
    report = "Task repair-1 failed after three attempts. Repository and evidence retained."
    plan: list[dict[str, Any]] = [
        {
            "step": "Inspect",
            "status": "in_progress" if observe_only else "pending",
            "verifies": True,
        },
        {"step": "Report", "status": "pending"},
    ]
    if not observe_only:
        plan.insert(0, {"step": "Schedule", "status": "in_progress"})
    responses = [tool_response("skill_view", {"name": _SKILL})]
    if not observe_only:
        responses.append(
            batch(
                tool_response("update_plan", {"plan": plan}),
                tool_response("schedule_ci_repair_loop", {"demo": True}),
            )
        )
    inspect_plan = [dict(item) for item in plan]
    if not observe_only:
        inspect_plan[0]["status"] = "completed"
    inspect_plan[-2]["status"] = "in_progress"
    report_plan = [dict(item) for item in inspect_plan]
    report_plan[-2]["status"] = "completed"
    report_plan[-1]["status"] = "in_progress"
    responses.extend(
        [
            batch(
                tool_response("update_plan", {"plan": inspect_plan}),
                tool_response("get_ci_repair_loop", {"task_id": "repair-1", "wait_seconds": 60}),
            ),
            tool_response("update_plan", {"plan": report_plan}),
            no_tool_response(report),
        ]
    )
    workflow = SkillWorkflow(Path(__file__).with_name("SKILL.md"), responses)
    workflow.session.available_capabilities["hosted_gateway"] = ()
    agent = workflow.build(
        [
            workflow.external(
                "schedule_ci_repair_loop",
                [
                    {
                        "ok": True,
                        "task_id": "repair-1",
                        "reused": True,
                        "deadline": 600,
                        "status": "running",
                    }
                ],
            ),
            workflow.external(
                "get_ci_repair_loop",
                [
                    {
                        "ok": True,
                        "task_id": "repair-1",
                        "status": "failed",
                        "terminal": True,
                        "response_text": report,
                    }
                ],
            ),
        ]
    )

    result = agent.handle(
        "Inspect and wait for existing task repair-1."
        if observe_only
        else "Run the selected private demo on this gateway.",
        BINDING,
    )

    expected = [] if observe_only else [("schedule_ci_repair_loop", {"demo": True})]
    assert workflow.calls == [
        *expected,
        ("get_ci_repair_loop", {"task_id": "repair-1", "wait_seconds": 60}),
    ]
    assert report in result.primary_response_text
    assert workflow.session.pending_user_choice is None
    workflow.assert_finished()

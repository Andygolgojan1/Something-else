"""Skill context survives answers and slash commands, but not unrelated requests."""

from types import SimpleNamespace

import pytest

from config.constants.capabilities import HOSTED_GATEWAY_CAPABILITY
from config.constants.skills import DELEGATING_GITHUB_CI_REPAIRS_SKILL_NAME
from core.agent_harness import SessionCore
from core.agent_harness.session.capabilities import withhold_capabilities
from core.agent_harness.session.pending_choice import AskUserQuestion, format_ask_user_answers
from core.agent_harness.turns.skill_activation import prepare_active_skill
from core.agent_harness.turns.turn_snapshot import TurnSnapshot


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Inspect a deployment", None),
        ("/auto high", "analyzing-github-ci-performance"),
        (
            format_ask_user_answers(
                (AskUserQuestion(label="", title="Repository?", options=("acme/one",)),),
                ("acme/one",),
            ),
            "analyzing-github-ci-performance",
        ),
    ],
)
def test_request_boundaries_preserve_only_the_current_flow(
    message: str, expected: str | None
) -> None:
    session = SimpleNamespace(active_skill="analyzing-github-ci-performance")
    prepare_active_skill(session, message)
    assert session.active_skill == expected


def test_an_answer_does_not_keep_a_skill_this_host_withholds() -> None:
    """A gateway session saved with the shell-only skill active drops it on the next answer."""
    session = SessionCore()
    withhold_capabilities(session, HOSTED_GATEWAY_CAPABILITY)
    session.active_skill = DELEGATING_GITHUB_CI_REPAIRS_SKILL_NAME
    answer = format_ask_user_answers(
        (AskUserQuestion(label="", title="Remote Repair Plan", options=("Use an existing PR",)),),
        ("Use an existing PR",),
    )

    # The prompt's ACTIVE SKILL block reads the snapshot taken before the turn runs.
    assert TurnSnapshot.from_session(answer, session, surface=None).active_skill is None
    prepare_active_skill(session, answer)
    assert session.active_skill is None

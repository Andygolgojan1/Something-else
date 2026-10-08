"""Every registered tool declares what it can change.

The read-only tool policy and ``opensre ask`` both refuse a tool with no
declared side-effect level, so an undeclared tool silently disappears from
read-only investigations. A new tool must pick a level.
"""

from __future__ import annotations

from tools.registry import get_registered_tools


def test_every_registered_tool_declares_a_side_effect_level() -> None:
    undeclared = sorted(
        tool.name
        for tool in get_registered_tools()
        if tool.side_effect_level is None and not tool.requires_approval
    )

    assert undeclared == [], (
        "Declare side_effect_level (NONE, READ_ONLY, MUTATING, or EXTERNAL) on: "
        + ", ".join(undeclared)
    )

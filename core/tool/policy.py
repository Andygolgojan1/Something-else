"""Operator tool policy enforced by the executor for every surface.

``OPENSRE_TOOL_POLICY=read_only`` refuses any tool that is not declared
``NONE`` or ``READ_ONLY``, any tool that requires approval, and any tool that
declares no level at all (fail closed). No hook or approval can lift it;
``OPENSRE_TOOL_POLICY_ALLOW`` names the tools an operator exempts on purpose.
"""

from __future__ import annotations

import os
from typing import Any

from config.constants.sovereign import (
    TOOL_POLICY_ALLOW_ENV,
    TOOL_POLICY_ENV,
    TOOL_POLICY_READ_ONLY,
)
from core.tool.contracts import SideEffectLevel

_READ_ONLY_LEVELS = frozenset({SideEffectLevel.NONE, SideEffectLevel.READ_ONLY})


def read_only_policy_enabled() -> bool:
    """Return whether the operator set ``OPENSRE_TOOL_POLICY=read_only``."""
    return os.getenv(TOOL_POLICY_ENV, "").strip().lower() == TOOL_POLICY_READ_ONLY


def _allowed_tool_names() -> frozenset[str]:
    raw = os.getenv(TOOL_POLICY_ALLOW_ENV, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def tool_policy_violation(tool: Any, tool_name: str) -> str | None:
    """Return why the active policy refuses ``tool``, or ``None`` when it may run."""
    if not read_only_policy_enabled() or tool_name in _allowed_tool_names():
        return None
    if bool(getattr(tool, "requires_approval", False)):
        reason = "it requires approval"
    else:
        level = getattr(tool, "side_effect_level", None)
        if level in _READ_ONLY_LEVELS:
            return None
        reason = (
            "it declares no side-effect level"
            if level is None
            else f"its side-effect level is {SideEffectLevel(level).value}"
        )
    return (
        f"{tool_name} is blocked by the read-only tool policy ({TOOL_POLICY_ENV}=read_only) "
        f"because {reason}. Continue the investigation with read-only tools, and tell the "
        "user what you would have done instead."
    )


__all__ = ["read_only_policy_enabled", "tool_policy_violation"]

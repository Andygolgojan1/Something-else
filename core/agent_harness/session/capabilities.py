"""Which capabilities a host offers on a session.

``SessionCore.available_capabilities`` maps a capability name to the tools the
host offers for it; an empty tuple means "this host has none". The harness
reads that map when it plans a turn, so the shape belongs here — a host states
what it withholds and never pokes the mapping itself.
"""

from __future__ import annotations

from typing import Any

from config.constants.skill_prerequisites import SKILL_REQUIRED_CAPABILITIES


def withhold_capabilities(session: Any, *names: str) -> None:
    """Record that this host offers no tools for ``names``.

    Idempotent, so a host may state its policy wherever a session is prepared
    without tracking whether an earlier call already did. A session without the
    mapping (a stub in a test) is left alone rather than grown one.
    """
    capabilities = getattr(session, "available_capabilities", None)
    if not isinstance(capabilities, dict):
        return
    for name in names:
        capabilities[name] = ()


def withheld_skill_capability(session: Any, skill_name: str | None) -> str | None:
    """The first capability ``skill_name`` needs that this session withholds, if any.

    A skill that needs a withheld capability cannot run on this host: the
    gateway withholds the hosted-gateway tools its shell-only skills drive.
    """
    capabilities = getattr(session, "available_capabilities", None)
    if not skill_name or not isinstance(capabilities, dict):
        return None
    return next(
        (
            name
            for name in SKILL_REQUIRED_CAPABILITIES.get(skill_name, ())
            if capabilities.get(name) == ()
        ),
        None,
    )


__all__ = ["withheld_skill_capability", "withhold_capabilities"]

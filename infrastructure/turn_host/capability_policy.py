"""Record the gateway's scheduler capabilities without withholding tools."""

from __future__ import annotations

from typing import Any

from config.constants.capabilities import SCHEDULER_HOST_CAPABILITY, SCHEDULER_HOST_IN_PROCESS


def ensure_gateway_capability_policy(session: Any, *, hosts_scheduler: bool = False) -> None:
    """Record whether the gateway hosts the scheduler, preserving existing capabilities.

    A gateway that runs the scheduler in-process says so: a scheduling tool then
    registers its task with the store instead of installing an OS-level service
    the container cannot run.
    """
    if hosts_scheduler:
        capabilities = getattr(session, "available_capabilities", None)
        if isinstance(capabilities, dict):
            capabilities[SCHEDULER_HOST_CAPABILITY] = (SCHEDULER_HOST_IN_PROCESS,)


__all__ = [
    "ensure_gateway_capability_policy",
]

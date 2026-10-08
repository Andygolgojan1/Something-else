"""Environment switches that keep incident data inside the operator's infrastructure."""

from __future__ import annotations

from typing import Final

SOVEREIGN_MODE_ENV: Final[str] = "OPENSRE_SOVEREIGN_MODE"
TOOL_POLICY_ENV: Final[str] = "OPENSRE_TOOL_POLICY"
TOOL_POLICY_ALLOW_ENV: Final[str] = "OPENSRE_TOOL_POLICY_ALLOW"
TOOL_POLICY_READ_ONLY: Final[str] = "read_only"

__all__ = [
    "SOVEREIGN_MODE_ENV",
    "TOOL_POLICY_ALLOW_ENV",
    "TOOL_POLICY_ENV",
    "TOOL_POLICY_READ_ONLY",
]

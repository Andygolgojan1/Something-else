"""Sovereign mode: no OpenSRE-hosted model, account, analytics, or error reporting.

When enabled, the process behaves as if no OpenSRE account token exists (so the
hosted LLM route and every webapp account call are off), product analytics and
Sentry are disabled, and the interactive shell starts without the sign-in gate.
Model calls then go only to the provider configured with ``LLM_PROVIDER``.
"""

from __future__ import annotations

import os

from config.constants.sovereign import SOVEREIGN_MODE_ENV

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def sovereign_mode_enabled() -> bool:
    """Return whether ``OPENSRE_SOVEREIGN_MODE`` is set to a truthy value."""
    return os.getenv(SOVEREIGN_MODE_ENV, "").strip().lower() in _TRUTHY


__all__ = ["sovereign_mode_enabled"]

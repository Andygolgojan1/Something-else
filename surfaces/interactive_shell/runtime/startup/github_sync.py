"""Pull the workspace GitHub connection into the local store as the shell starts."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from infrastructure.analytics.source import is_test_run

if TYPE_CHECKING:
    from surfaces.interactive_shell.runtime import Session

logger = logging.getLogger(__name__)


def start_workspace_github_sync(session: Session) -> threading.Thread | None:
    """Sync in the background so a slow webapp never delays the prompt.

    A change lands in the store; the session re-resolves integrations so the
    next turn sees GitHub connected (or gone) without a restart.
    """
    if is_test_run():
        return None

    def _run() -> None:
        from integrations.github import sync_workspace_github

        try:
            result = sync_workspace_github()
        except Exception:
            logger.debug("[github-sync] startup sync failed", exc_info=True)
            return
        if result.changed:
            session.refresh_integration_state()

    thread = threading.Thread(target=_run, name="opensre-github-workspace-sync", daemon=True)
    thread.start()
    return thread


__all__ = ["start_workspace_github_sync"]

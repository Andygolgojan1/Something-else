"""Process-local handled-event store for Socket Mode, bounded in time and size.

Socket Mode has exactly one consumer per app token, so a store held by that
process sees every redelivery of an event. Events API HTTP cannot rely on that
(any replica may get the retry) and uses the shared store instead.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import NamedTuple

from config.constants.slack import (
    SLACK_SOCKET_MODE_DEDUP_MAX_EVENTS,
    SLACK_SOCKET_MODE_DEDUP_RETRY_WINDOW_SECONDS,
    SLACK_SOCKET_MODE_DEDUP_TTL_SECONDS,
)
from gateway.core.storage.events.repository import ABANDONED_CLAIM_SECONDS


class _Handled(NamedTuple):
    at: float
    committed: bool


class BoundedHandledSlackEventRepository:
    """:class:`HandledSlackEventRepository` that forgets entries after a TTL or past a size cap.

    Same claim semantics as the shared store: a claim is provisional until
    confirmed, a provisional claim younger than ``abandoned_after_seconds``
    refuses a concurrent duplicate, and a released one is free again. Socket
    Mode runs listeners on several threads, so every method takes the lock.
    Size eviction drops the oldest entry first, but never one younger than
    ``retry_window_seconds``: Slack may still redeliver that event, and its
    work may still be queued or running. A burst can then exceed the cap
    until those entries age out of the window.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = SLACK_SOCKET_MODE_DEDUP_TTL_SECONDS,
        max_events: int = SLACK_SOCKET_MODE_DEDUP_MAX_EVENTS,
        retry_window_seconds: float = SLACK_SOCKET_MODE_DEDUP_RETRY_WINDOW_SECONDS,
        abandoned_after_seconds: float = ABANDONED_CLAIM_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        # Insertion order is age order: every write moves its key to the end
        # with the current time, so expiry only ever inspects the front.
        self._entries: OrderedDict[str, _Handled] = OrderedDict()
        self._ttl = ttl_seconds
        self._max_events = max_events
        self._retry_window = retry_window_seconds
        self._abandoned_after = abandoned_after_seconds
        self._now = now
        self._lock = threading.Lock()

    def claim(self, event_id: str) -> bool:
        with self._lock:
            now = self._now()
            self._expire(now)
            entry = self._entries.get(event_id)
            if entry is not None and (entry.committed or now - entry.at < self._abandoned_after):
                return False
            self._write(event_id, _Handled(at=now, committed=False))
            return True

    def release(self, event_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(event_id)
            if entry is not None and not entry.committed:
                del self._entries[event_id]
        return True

    def confirm(self, event_id: str) -> bool:
        with self._lock:
            self._write(event_id, _Handled(at=self._now(), committed=True))
        return True

    def _write(self, event_id: str, entry: _Handled) -> None:
        self._entries[event_id] = entry
        self._entries.move_to_end(event_id)
        while len(self._entries) > self._max_events:
            _oldest_id, oldest = next(iter(self._entries.items()))
            if entry.at - oldest.at < self._retry_window:
                # Every remaining entry is at least this young; keep them all.
                return
            self._entries.popitem(last=False)

    def _expire(self, now: float) -> None:
        while self._entries:
            oldest_id, oldest = next(iter(self._entries.items()))
            if now - oldest.at < self._ttl:
                return
            del self._entries[oldest_id]


__all__ = ["BoundedHandledSlackEventRepository"]

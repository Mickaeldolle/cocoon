"""Small per-user generation limiter for the single-process API deployment."""

import threading
from collections import deque
from time import monotonic
from uuid import UUID


class AssistantRateLimiter:
    def __init__(self) -> None:
        self._events: dict[UUID, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def allow(self, user_id: UUID, limit: int, *, now: float | None = None) -> bool:
        moment = monotonic() if now is None else now
        cutoff = moment - 60
        with self._lock:
            if moment - self._last_cleanup >= 60:
                for key, events in list(self._events.items()):
                    while events and events[0] <= cutoff:
                        events.popleft()
                    if not events:
                        del self._events[key]
                self._last_cleanup = moment
            events = self._events.setdefault(user_id, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(moment)
            return True


assistant_rate_limiter = AssistantRateLimiter()

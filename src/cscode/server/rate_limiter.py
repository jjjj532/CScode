"""In-memory sliding-window rate limiter.

Usage:
    limiter = RateLimiter(max_requests=60, window_seconds=60)
    if not limiter.check(client_ip):
        raise HTTPException(status_code=429)
"""

from __future__ import annotations

import collections
import time
from typing import Callable


class RateLimiter:
    """Sliding-window rate limiter keyed by IP address.

    Thread-safe for asyncio use (single-threaded event loop).
    Default: 60 requests per 60 seconds per IP.
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._time = time_func or time.monotonic
        self._windows: dict[str, collections.deque[float]] = {}

    def check(self, ip: str) -> bool:
        """Check if *ip* is under the rate limit.

        Returns True if the request is allowed, False if rate limited.
        """
        if self._max <= 0:
            return False

        now = self._time()
        timestamps = self._windows.get(ip)
        if timestamps is None:
            self._windows[ip] = collections.deque([now], maxlen=self._max + 1)
            return True

        # Evict timestamps outside the window
        cutoff = now - self._window
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= self._max:
            return False

        timestamps.append(now)
        return True

    def cleanup(self) -> None:
        """Remove stale entries (IPs with no recent requests)."""
        now = self._time()
        cutoff = now - self._window
        stale = [ip for ip, ts in self._windows.items() if not ts or ts[-1] < cutoff]
        for ip in stale:
            del self._windows[ip]

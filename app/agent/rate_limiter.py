"""
rate_limiter.py — Per-tenant sliding-window rate limiter.

Enforces two independent limits per tenant, both using a sliding window:
  - requests_per_minute  (short burst protection)
  - requests_per_day     (daily spend cap)

A limit of 0 means unlimited (use for internal/trusted tenants).

IMPLEMENTATION
  Pure in-memory using collections.deque per (tenant_id, window) key.
  Each entry is a UTC timestamp; entries older than the window are evicted
  on every check so memory stays bounded.

  This is intentionally simple — it fits the current single-process deployment.
  For a multi-process or distributed deployment, replace the deque store with
  Redis (e.g. redis-py with ZADD/ZREMRANGEBYSCORE) using the same interface.

USAGE (in chat.py)
  limiter = get_rate_limiter()
  allowed, retry_after = limiter.check(tenant_id, rpm, rpd)
  if not allowed:
      raise HTTPException(429, detail=f"Rate limit exceeded. Retry after {retry_after}s.")
"""
from __future__ import annotations

import threading
import time
from collections import deque


class TenantRateLimiter:
    """
    Thread-safe sliding-window rate limiter keyed on tenant_id.

    Two windows are tracked independently per tenant:
      - 60-second window  → enforces requests_per_minute
      - 86400-second window → enforces requests_per_day
    """

    _MINUTE  = 60
    _DAY     = 86_400

    def __init__(self) -> None:
        # {(tenant_id, window_seconds): deque[float]}
        self._windows: dict[tuple[str, int], deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        tenant_id: str,
        requests_per_minute: int,
        requests_per_day: int,
    ) -> tuple[bool, int]:
        """
        Record a request attempt and check whether it is within limits.

        Parameters
        ----------
        tenant_id           : unique tenant identifier
        requests_per_minute : max allowed in the last 60 s (0 = unlimited)
        requests_per_day    : max allowed in the last 24 h (0 = unlimited)

        Returns
        -------
        (allowed, retry_after_seconds)
          allowed       — True if the request should proceed
          retry_after   — seconds until the oldest blocking request ages out;
                          0 when allowed=True
        """
        now = time.time()
        with self._lock:
            for window, limit in (
                (self._MINUTE, requests_per_minute),
                (self._DAY,    requests_per_day),
            ):
                if limit == 0:
                    continue  # unlimited for this window

                key = (tenant_id, window)
                if key not in self._windows:
                    self._windows[key] = deque()
                dq = self._windows[key]

                # Evict timestamps outside the window
                cutoff = now - window
                while dq and dq[0] <= cutoff:
                    dq.popleft()

                if len(dq) >= limit:
                    # Oldest entry determines when a slot opens
                    retry_after = int(dq[0] - cutoff) + 1
                    return False, retry_after

            # Both windows OK — record this request in both
            for window, limit in (
                (self._MINUTE, requests_per_minute),
                (self._DAY,    requests_per_day),
            ):
                if limit == 0:
                    continue
                key = (tenant_id, window)
                if key not in self._windows:
                    self._windows[key] = deque()
                self._windows[key].append(now)

        return True, 0

    def current_usage(self, tenant_id: str) -> dict[str, int]:
        """Return current request counts for observability/debugging."""
        now = time.time()
        with self._lock:
            minute_key = (tenant_id, self._MINUTE)
            day_key    = (tenant_id, self._DAY)

            def _count(key: tuple, window: int) -> int:
                dq = self._windows.get(key, deque())
                cutoff = now - window
                return sum(1 for t in dq if t > cutoff)

            return {
                "last_minute": _count(minute_key, self._MINUTE),
                "last_day":    _count(day_key,    self._DAY),
            }


# ── Process-level singleton ───────────────────────────────────────────────────
# One instance shared across all requests in this process.
_limiter = TenantRateLimiter()


def get_rate_limiter() -> TenantRateLimiter:
    """Return the process-level rate limiter singleton."""
    return _limiter

from collections import defaultdict, deque
import threading
import time

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter for single-instance protection."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, max_requests: int, window_seconds: int) -> int | None:
        """Record an attempt and return Retry-After seconds if limit is exceeded, else None."""
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= max_requests:
                retry_after = max(1, int(bucket[0] + window_seconds - now) + 1)
                return retry_after

            bucket.append(now)
            return None

    def reset(self) -> None:
        """Clear all recorded rate-limit windows."""
        with self._lock:
            self._events.clear()


def extract_client_ip(request: Request) -> str:
    """Resolve the client IP address for rate-limiting purposes."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    limiter: SlidingWindowRateLimiter,
    *,
    keys: list[str],
    max_requests: int,
    window_seconds: int,
    detail: str = "Too many requests. Please wait before trying again.",
) -> None:
    """Check one or more rate-limit keys and raise HTTP 429 if any bucket is exhausted."""
    retry_delays: list[int] = []
    for key in keys:
        retry_after = limiter.check(
            key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if retry_after is not None:
            retry_delays.append(retry_after)

    if retry_delays:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(max(retry_delays))},
        )

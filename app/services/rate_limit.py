"""In-process sliding window rate limiter."""

from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import time

from app.config import get_settings


@dataclass
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class SlidingWindowRateLimiter:
    def __init__(self, *, window_seconds: int, max_requests: int) -> None:
        self.window_seconds = max(window_seconds, 1)
        self.max_requests = max(max_requests, 1)
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> RateLimitDecision:
        now = time()
        window_start = now - self.window_seconds
        with self._lock:
            history = self._events.setdefault(key, deque())
            while history and history[0] <= window_start:
                history.popleft()

            if len(history) >= self.max_requests:
                retry_after = int(max(1, self.window_seconds - (now - history[0])))
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    remaining=0,
                )

            history.append(now)
            remaining = max(0, self.max_requests - len(history))
            return RateLimitDecision(
                allowed=True,
                retry_after_seconds=0,
                remaining=remaining,
            )


_chat_limiter: SlidingWindowRateLimiter | None = None


def get_chat_rate_limiter() -> SlidingWindowRateLimiter:
    global _chat_limiter
    if _chat_limiter is None:
        cfg = get_settings()
        _chat_limiter = SlidingWindowRateLimiter(
            window_seconds=cfg.rate_limit_window_seconds,
            max_requests=cfg.rate_limit_max_requests,
        )
    return _chat_limiter


def reset_chat_rate_limiter() -> None:
    global _chat_limiter
    _chat_limiter = None

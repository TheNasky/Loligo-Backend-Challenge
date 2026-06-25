"""Simple in-memory idempotency cache for chat requests."""

from dataclasses import dataclass
from threading import Lock
from time import time

from app.config import get_settings


@dataclass
class IdempotentValue:
    expires_at: float
    payload: dict


class IdempotencyCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = max(ttl_seconds, 1)
        self._values: dict[str, IdempotentValue] = {}
        self._lock = Lock()

    def get(self, key: str) -> dict | None:
        now = time()
        with self._lock:
            self._cleanup(now)
            entry = self._values.get(key)
            if entry is None:
                return None
            return dict(entry.payload)

    def set(self, key: str, payload: dict) -> None:
        expires_at = time() + self.ttl_seconds
        with self._lock:
            self._cleanup(time())
            self._values[key] = IdempotentValue(expires_at=expires_at, payload=dict(payload))

    def _cleanup(self, now: float) -> None:
        expired = [k for k, v in self._values.items() if v.expires_at <= now]
        for key in expired:
            self._values.pop(key, None)


_cache: IdempotencyCache | None = None


def get_idempotency_cache() -> IdempotencyCache:
    global _cache
    if _cache is None:
        _cache = IdempotencyCache(ttl_seconds=get_settings().idempotency_ttl_seconds)
    return _cache


def reset_idempotency_cache() -> None:
    global _cache
    _cache = None

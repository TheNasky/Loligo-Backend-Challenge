"""Shared resilience helpers for upstream I/O calls."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from time import sleep
from typing import Callable, TypeVar

T = TypeVar("T")

_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="upstream-io")


class OperationTimeoutError(TimeoutError):
    """Operation exceeded timeout budget."""


def run_with_timeout(
    operation: Callable[[], T],
    *,
    timeout_seconds: float,
    operation_name: str,
) -> T:
    future = _EXECUTOR.submit(operation)
    try:
        return future.result(timeout=max(timeout_seconds, 0.1))
    except FuturesTimeoutError as exc:
        future.cancel()
        raise OperationTimeoutError(
            f"{operation_name} timed out after {timeout_seconds:.2f}s"
        ) from exc


def run_with_resilience(
    operation: Callable[[], T],
    *,
    timeout_seconds: float,
    attempts: int,
    backoff_seconds: float,
    operation_name: str,
) -> T:
    max_attempts = max(attempts, 1)
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return run_with_timeout(
                operation,
                timeout_seconds=timeout_seconds,
                operation_name=operation_name,
            )
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts:
                raise
            sleep(max(backoff_seconds, 0.0) * attempt)

    assert last_exc is not None
    raise last_exc

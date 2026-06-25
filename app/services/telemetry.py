"""Very small in-memory telemetry counters."""

from threading import Lock


class TelemetryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._chat_requests_total = 0
        self._chat_errors_total = 0
        self._chat_rate_limited_total = 0
        self._chat_latency_ms_sum = 0.0

    def record_chat_success(self, latency_ms: float) -> None:
        with self._lock:
            self._chat_requests_total += 1
            self._chat_latency_ms_sum += max(latency_ms, 0.0)

    def record_chat_error(self) -> None:
        with self._lock:
            self._chat_requests_total += 1
            self._chat_errors_total += 1

    def record_rate_limited(self) -> None:
        with self._lock:
            self._chat_rate_limited_total += 1

    def snapshot(self) -> dict:
        with self._lock:
            avg_latency = 0.0
            if self._chat_requests_total > 0:
                avg_latency = self._chat_latency_ms_sum / self._chat_requests_total
            return {
                "chat_requests_total": self._chat_requests_total,
                "chat_errors_total": self._chat_errors_total,
                "chat_rate_limited_total": self._chat_rate_limited_total,
                "chat_latency_avg_ms": round(avg_latency, 2),
            }


_telemetry = TelemetryStore()


def get_telemetry() -> TelemetryStore:
    return _telemetry

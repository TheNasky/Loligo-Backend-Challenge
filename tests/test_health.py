from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "timestamp" in body


def test_metrics_returns_counters() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "chat_requests_total" in body
    assert "chat_errors_total" in body
    assert "chat_latency_avg_ms" in body

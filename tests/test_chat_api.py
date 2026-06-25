from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agent.loop import AgentLoopResult
from app.main import app
from app.services.idempotency import reset_idempotency_cache
from app.memory.store import reset_conversation_store
from app.services.rate_limit import RateLimitDecision
from app.services.rate_limit import reset_chat_rate_limiter

client = TestClient(app)


def setup_function() -> None:
    reset_conversation_store()
    reset_chat_rate_limiter()
    reset_idempotency_cache()


def test_post_chat_returns_reply_with_mocked_agent() -> None:
    conversation_id = f"api-test-{uuid4().hex}"
    with patch("app.api.chat.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = "test-key"
        with patch("app.api.chat.get_llm"), patch("app.api.chat.agent_loop") as mock_loop:
            mock_loop.return_value = AgentLoopResult(
                reply="KLAC is oversold with RSI near 30.",
                tool_calls=[{"name": "get_market_data", "input": {"ticker": "KLAC", "action": "snapshot"}}],
            )

            response = client.post(
                "/chat",
                json={"id": conversation_id, "message": "Analyze KLAC"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == conversation_id
    assert "KLAC" in body["reply"]
    assert len(body["tool_calls"]) == 1


def test_get_chat_returns_history_after_post() -> None:
    conversation_id = f"api-test-{uuid4().hex}"
    with patch("app.api.chat.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = "test-key"
        with patch("app.api.chat.get_llm"), patch("app.api.chat.agent_loop") as mock_loop:
            mock_loop.return_value = AgentLoopResult(reply="Hello from agent", tool_calls=[])

            post = client.post(
                "/chat",
                json={"id": conversation_id, "message": "Hi"},
            )
            assert post.status_code == 200

            get = client.get(f"/chat/{conversation_id}")
            assert get.status_code == 200
            history = get.json()
            assert history["id"] == conversation_id
            assert len(history["messages"]) == 2
            assert history["messages"][0]["role"] == "user"
            assert history["messages"][1]["role"] == "assistant"


def test_get_unknown_conversation_returns_404() -> None:
    response = client.get("/chat/does-not-exist-xyz")
    assert response.status_code == 404


def test_post_empty_message_returns_422() -> None:
    response = client.post("/chat", json={"id": "x", "message": "   "})
    assert response.status_code == 422


def test_post_without_api_key_returns_503() -> None:
    with patch("app.api.chat.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = ""
        response = client.post("/chat", json={"id": "x", "message": "hello"})
    assert response.status_code == 503


def test_post_chat_persists_tool_messages() -> None:
    conversation_id = f"api-test-tools-{uuid4().hex}"
    with patch("app.api.chat.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = "test-key"
        with patch("app.api.chat.get_llm"), patch("app.api.chat.agent_loop") as mock_loop:
            mock_loop.return_value = AgentLoopResult(
                reply="Done.",
                tool_calls=[{"name": "get_market_data", "input": {"ticker": "AAPL"}}],
                tool_outputs=[
                    {
                        "name": "get_market_data",
                        "input": {"ticker": "AAPL"},
                        "output": {"ticker": "AAPL", "price": 200},
                    }
                ],
            )

            post = client.post("/chat", json={"id": conversation_id, "message": "Analyze AAPL"})
            assert post.status_code == 200

            get = client.get(f"/chat/{conversation_id}")
            assert get.status_code == 200
            messages = get.json()["messages"]
            assert len(messages) == 3
            assert messages[1]["role"] == "tool"
            assert messages[1]["tool_name"] == "get_market_data"


def test_post_chat_returns_429_when_rate_limited() -> None:
    mocked_limiter = MagicMock()
    mocked_limiter.allow.return_value = RateLimitDecision(
        allowed=False,
        retry_after_seconds=10,
        remaining=0,
    )
    with patch("app.api.chat.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = "test-key"
        with patch("app.api.chat.get_chat_rate_limiter", return_value=mocked_limiter):
            response = client.post("/chat", json={"id": "limited", "message": "hello"})
    assert response.status_code == 429


def test_post_chat_idempotency_key_reuses_response() -> None:
    conversation_id = f"api-test-idem-{uuid4().hex}"
    with patch("app.api.chat.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = "test-key"
        with patch("app.api.chat.get_llm"), patch("app.api.chat.agent_loop") as mock_loop:
            mock_loop.return_value = AgentLoopResult(reply="Same reply", tool_calls=[])

            headers = {"Idempotency-Key": "k1"}
            first = client.post(
                "/chat",
                json={"id": conversation_id, "message": "Hello"},
                headers=headers,
            )
            second = client.post(
                "/chat",
                json={"id": conversation_id, "message": "Hello"},
                headers=headers,
            )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert second.headers.get("X-Idempotency-Replayed") == "true"
    assert mock_loop.call_count == 1

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.agent.loop import MAX_ITERATIONS, agent_loop
from app.agent.tools import get_market_data
from app.memory.store import Message


@tool
def _echo_tool(value: str) -> str:
    """Echo a value for testing."""
    return json.dumps({"echo": value})


def test_get_market_data_quote_mocked() -> None:
    with patch("app.services.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_info = MagicMock()
        mock_info.last_price = 150.25
        mock_info.previous_close = 148.0
        mock_info.currency = "USD"

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info
        mock_ticker_cls.return_value = mock_ticker

        raw = get_market_data.invoke({"ticker": "AAPL", "action": "quote"})
        data = json.loads(raw)

    assert data["ticker"] == "AAPL"
    assert data["price"] == 150.25
    assert data["action"] == "quote"


def test_get_market_data_invalid_ticker_returns_error_shape() -> None:
    with patch("app.services.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.fast_info = MagicMock(last_price=None, previous_close=None)
        mock_ticker.history.return_value.empty = True
        mock_ticker_cls.return_value = mock_ticker

        raw = get_market_data.invoke({"ticker": "BADXYZ", "action": "quote"})
        data = json.loads(raw)

    assert "error" in data


def test_agent_loop_direct_reply_without_tools() -> None:
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    mock_bound.invoke.return_value = AIMessage(content="AAPL looks extended.")

    result = agent_loop(
        conversation_id="t1",
        user_message="Thoughts on AAPL?",
        history=[],
        llm=mock_llm,
        tools=[_echo_tool],
    )

    assert result.reply == "AAPL looks extended."
    assert result.tool_calls == []


def test_agent_loop_executes_tool_then_replies() -> None:
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound

    mock_bound.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "_echo_tool", "args": {"value": "ping"}, "id": "call-1"},
            ],
        ),
        AIMessage(content="Tool said ping."),
    ]

    result = agent_loop(
        conversation_id="t2",
        user_message="run echo",
        history=[],
        llm=mock_llm,
        tools=[_echo_tool],
    )

    assert result.reply == "Tool said ping."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "_echo_tool"


def test_agent_loop_max_iterations_fallback() -> None:
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    mock_bound.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{"name": "_echo_tool", "args": {"value": "x"}, "id": "call-loop"}],
    )

    result = agent_loop(
        conversation_id="t3",
        user_message="loop forever",
        history=[],
        llm=mock_llm,
        tools=[_echo_tool],
    )

    assert mock_bound.invoke.call_count == MAX_ITERATIONS
    assert "couldn't finish" in result.reply.lower()

"""LangChain tools exposed to the agent."""

import json
from typing import Literal

from langchain_core.tools import tool

from app.services.news import fetch_ticker_news
from app.services.screening import scan_trading_setups
from app.services.yahoo import fetch_quote, fetch_recent_history, fetch_snapshot


@tool
def get_market_data(
    ticker: str,
    action: Literal["quote", "history", "snapshot"] = "snapshot",
) -> str:
    """
    Fetch Yahoo Finance market data for a stock ticker.

    Use action='quote' for current price only.
    Use action='history' for recent daily closes.
    Use action='snapshot' for price + RSI, MAs, 20-day range (preferred for analysis).
    """
    if action == "quote":
        result = fetch_quote(ticker)
    elif action == "history":
        result = fetch_recent_history(ticker)
    else:
        result = fetch_snapshot(ticker)
    return json.dumps(result)


@tool
def get_ticker_news(ticker: str, limit: int = 8) -> str:
    """
    Fetch recent Yahoo Finance news headlines for a ticker.

    Use when the user asks about catalysts, news, or whether to buy/sell with context.
    Summarize headlines — do not invent articles.
    """
    result = fetch_ticker_news(ticker, limit=min(max(limit, 1), 10))
    return json.dumps(result)


@tool
def scan_market_setups(per_strategy: int = 4) -> str:
    """
    Scan liquid stocks and return top picks grouped by strategy: momentum, trend, breakout, pullback, range.

    Use for broad market scans. Present results across ALL strategy buckets equally.
    Do NOT reduce output to only pullback or mean-reversion names.
    """
    result = scan_trading_setups(per_strategy=min(max(per_strategy, 1), 6))
    return json.dumps(result)


def get_agent_tools() -> list:
    """All tools bound to the agent."""
    return [get_market_data, get_ticker_news, scan_market_setups]

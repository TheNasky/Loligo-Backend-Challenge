"""Yahoo Finance news headlines for ticker digest."""

from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from app.config import get_settings
from app.services.resilience import run_with_resilience
from app.services.yahoo import normalize_ticker


def fetch_ticker_news(ticker: str, limit: int = 8) -> dict[str, Any]:
    """Fetch recent headlines for a symbol (input to news digest narration)."""
    symbol = normalize_ticker(ticker)
    if not symbol:
        return {"error": "Ticker is required", "ticker": ticker}

    try:
        stock = yf.Ticker(symbol)
        cfg = get_settings()
        raw_news = run_with_resilience(
            lambda: stock.news or [],
            timeout_seconds=cfg.upstream_timeout_seconds,
            attempts=cfg.upstream_max_retries,
            backoff_seconds=cfg.upstream_retry_backoff_seconds,
            operation_name=f"yahoo.news({symbol})",
        )

        articles: list[dict[str, str]] = []
        for item in raw_news[:limit]:
            content = item.get("content") or item
            title = content.get("title") or item.get("title")
            if not title:
                continue
            articles.append(
                {
                    "title": str(title),
                    "publisher": str(content.get("provider", {}).get("displayName", "Unknown")),
                    "link": str(content.get("canonicalUrl", {}).get("url", item.get("link", ""))),
                }
            )

        if not articles:
            return {
                "ticker": symbol,
                "yahoo_symbol": symbol,
                "action": "news",
                "articles": [],
                "message": "No recent headlines found for this symbol",
                "as_of": datetime.now(UTC).isoformat(),
            }

        return {
            "ticker": symbol,
            "yahoo_symbol": symbol,
            "action": "news",
            "articles": articles,
            "count": len(articles),
            "as_of": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return {
            "error": f"Failed to fetch news: {exc}",
            "ticker": symbol,
            "yahoo_symbol": symbol,
        }

"""Yahoo Finance data access — pure Python, no LLM."""

from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from app.config import get_settings
from app.services.indicators import build_snapshot, classify_strategies
from app.services.resilience import run_with_resilience

MIN_HISTORY_BARS = 22
DEFAULT_HISTORY_DAYS = 60


def normalize_ticker(ticker: str) -> str:
    """Uppercase and strip user input."""
    return ticker.strip().upper()


def _error_payload(ticker: str, message: str) -> dict[str, Any]:
    return {
        "error": message,
        "ticker": ticker,
        "yahoo_symbol": normalize_ticker(ticker),
    }


def _resilience_kwargs() -> dict[str, int | float]:
    cfg = get_settings()
    return {
        "timeout_seconds": cfg.upstream_timeout_seconds,
        "attempts": cfg.upstream_max_retries,
        "backoff_seconds": cfg.upstream_retry_backoff_seconds,
    }


def fetch_quote(ticker: str) -> dict[str, Any]:
    """Live quote for a single ticker."""
    symbol = normalize_ticker(ticker)
    if not symbol:
        return _error_payload(ticker, "Ticker is required")

    try:
        stock = yf.Ticker(symbol)
        info = run_with_resilience(
            lambda: stock.fast_info,
            operation_name=f"yahoo.fast_info({symbol})",
            **_resilience_kwargs(),
        )
        price = getattr(info, "last_price", None) or getattr(info, "lastPrice", None)
        if price is None:
            # Fallback to recent daily bar
            hist = run_with_resilience(
                lambda: stock.history(period="5d", auto_adjust=True),
                operation_name=f"yahoo.history_quote_fallback({symbol})",
                **_resilience_kwargs(),
            )
            if hist.empty:
                return _error_payload(symbol, "No quote data found for symbol")
            price = float(hist["Close"].iloc[-1])

        prev_close = getattr(info, "previous_close", None) or getattr(
            info, "previousClose", None
        )
        change_percent = None
        if prev_close and prev_close > 0:
            change_percent = round(((float(price) - float(prev_close)) / float(prev_close)) * 100, 2)

        currency = getattr(info, "currency", None) or "USD"

        return {
            "ticker": symbol,
            "yahoo_symbol": symbol,
            "action": "quote",
            "price": round(float(price), 4),
            "currency": currency,
            "change_percent": change_percent,
            "as_of": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return _error_payload(symbol, f"Failed to fetch quote: {exc}")


def fetch_recent_history(ticker: str, days: int = DEFAULT_HISTORY_DAYS) -> dict[str, Any]:
    """Daily adjusted closes for the last N days."""
    symbol = normalize_ticker(ticker)
    if not symbol:
        return _error_payload(ticker, "Ticker is required")

    try:
        stock = yf.Ticker(symbol)
        hist = run_with_resilience(
            lambda: stock.history(period=f"{max(days, MIN_HISTORY_BARS)}d", auto_adjust=True),
            operation_name=f"yahoo.history({symbol})",
            **_resilience_kwargs(),
        )
        if hist.empty or len(hist) < MIN_HISTORY_BARS:
            return _error_payload(
                symbol,
                f"Insufficient history (need at least {MIN_HISTORY_BARS} daily bars)",
            )

        closes = [round(float(v), 4) for v in hist["Close"].tolist()]
        dates = [d.isoformat() for d in hist.index.to_pydatetime()]

        first_close = closes[0]
        last_close = closes[-1]
        change_pct = round(((last_close - first_close) / first_close) * 100, 2) if first_close else None

        return {
            "ticker": symbol,
            "yahoo_symbol": symbol,
            "action": "history",
            "days": len(closes),
            "closes": closes,
            "dates": dates,
            "change_percent": change_pct,
            "as_of": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return _error_payload(symbol, f"Failed to fetch history: {exc}")


def fetch_snapshot(ticker: str) -> dict[str, Any]:
    """Quote + technical snapshot (RSI, MAs, range) computed in Python."""
    symbol = normalize_ticker(ticker)
    history = fetch_recent_history(symbol)
    if "error" in history:
        return history

    quote = fetch_quote(symbol)
    if "error" in quote:
        return quote

    closes = history["closes"]
    snapshot = build_snapshot(closes, float(quote["price"]))
    tags = classify_strategies({**snapshot, "price": float(quote["price"])})

    return {
        "ticker": symbol,
        "yahoo_symbol": symbol,
        "action": "snapshot",
        "as_of": datetime.now(UTC).isoformat(),
        **quote,
        **snapshot,
        "strategy_tags": tags,
        "sparkline": closes[-30:],
        "history_days": history["days"],
        "change_percent_period": history.get("change_percent"),
    }

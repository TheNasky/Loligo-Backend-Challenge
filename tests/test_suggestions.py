"""Tests for dynamic suggestion chips."""

from unittest.mock import patch

from app.services.suggestions import build_suggestions, clear_suggestions_cache

MOCK_ROWS = [
    {
        "ticker": "NVDA",
        "price": 500.0,
        "rsi14": 62.0,
        "ma20": 480.0,
        "ma50": 450.0,
        "pct_vs_ma20": 4.2,
        "change_percent_period": 8.5,
        "range_20d": {"position_pct": 85},
        "strategy_tags": ["momentum", "trend", "breakout"],
    },
    {
        "ticker": "AMD",
        "price": 160.0,
        "rsi14": 48.0,
        "ma20": 155.0,
        "ma50": 150.0,
        "pct_vs_ma20": -2.1,
        "change_percent_period": -3.2,
        "range_20d": {"position_pct": 40},
        "strategy_tags": ["pullback", "range"],
    },
    {
        "ticker": "MSFT",
        "price": 420.0,
        "rsi14": 55.0,
        "ma20": 410.0,
        "ma50": 400.0,
        "pct_vs_ma20": 2.4,
        "change_percent_period": 3.1,
        "range_20d": {"position_pct": 70},
        "strategy_tags": ["trend"],
    },
]


def setup_function() -> None:
    clear_suggestions_cache()


@patch("app.services.suggestions._get_scan_rows")
def test_build_suggestions_uses_market_leaders(mock_rows) -> None:
    mock_rows.return_value = MOCK_ROWS

    payload = build_suggestions("en")
    labels = [s["label"] for s in payload["suggestions"]]
    messages = [s["message"] for s in payload["suggestions"]]

    assert payload["source"] == "yahoo_finance"
    assert len(payload["suggestions"]) >= 3
    assert len(payload["suggestions"]) <= 12
    assert not any("Pullback" in label for label in labels)
    assert not any("Breakout" in label for label in labels)
    assert any("moving today" in label.lower() for label in labels)
    assert any("NVDA" in msg or "MSFT" in msg for msg in messages)


@patch("app.services.suggestions._get_scan_rows")
def test_build_suggestions_spanish(mock_rows) -> None:
    mock_rows.return_value = MOCK_ROWS

    payload = build_suggestions("es")
    labels = [s["label"] for s in payload["suggestions"]]

    assert len(payload["suggestions"]) >= 3
    kinds = {s["kind"] for s in payload["suggestions"]}
    assert "overview" in kinds
    assert any("o" in label and "?" in label for label in labels)

"""Indicator unit tests."""

from app.services.indicators import (
    build_snapshot,
    calculate_rsi,
    classify_strategies,
    sma,
)


def test_sma_computes_last_window() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sma(values, 3) == 4.0


def test_rsi_returns_value_for_sufficient_data() -> None:
    closes = [44.0, 44.5, 43.8, 44.2, 43.5, 43.0, 42.5, 42.0, 41.5, 41.0,
              40.5, 40.0, 39.5, 39.0, 38.5, 38.0]
    rsi = calculate_rsi(closes, 14)
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_build_snapshot_includes_multi_strategy_fields() -> None:
    closes = [float(100 + i * 0.5) for i in range(30)]
    snapshot = build_snapshot(closes, current_price=95.0)
    assert snapshot["ma20"] is not None
    assert snapshot["rsi14"] is not None
    assert "pct_vs_ma20" in snapshot
    assert "low" in snapshot["range_20d"]


def test_classify_strategies_can_tag_pullback() -> None:
    tags = classify_strategies(
        {
            "price": 90.0,
            "rsi14": 28.0,
            "pct_vs_ma20": -8.0,
            "ma20": 98.0,
            "ma50": 95.0,
            "range_20d": {"position_pct": 10.0},
            "change_percent_period": -5.0,
        }
    )
    assert "pullback" in tags


def test_classify_strategies_can_tag_momentum() -> None:
    tags = classify_strategies(
        {
            "price": 110.0,
            "rsi14": 62.0,
            "pct_vs_ma20": 5.0,
            "ma20": 105.0,
            "ma50": 100.0,
            "range_20d": {"position_pct": 75.0},
            "change_percent_period": 8.0,
        }
    )
    assert "momentum" in tags

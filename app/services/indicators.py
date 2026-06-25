"""Deterministic technical indicators — never computed by the LLM."""

from typing import Any


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return round(sum(window) / len(window), 4)


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def build_snapshot(closes: list[float], current_price: float) -> dict[str, Any]:
    """Technical context for multi-strategy analysis."""
    ma20 = sma(closes, 20)
    ma50 = sma(closes, 50) if len(closes) >= 50 else None

    window = closes[-20:] if len(closes) >= 20 else closes
    low_20 = min(window)
    high_20 = max(window)
    range_span = high_20 - low_20
    range_position_pct = (
        round(((current_price - low_20) / range_span) * 100, 2) if range_span > 0 else None
    )

    pct_vs_ma20 = (
        round(((current_price - ma20) / ma20) * 100, 2) if ma20 and ma20 > 0 else None
    )

    rsi14 = calculate_rsi(closes, 14)

    period_change = None
    if len(closes) >= 2 and closes[0] > 0:
        period_change = round(((closes[-1] - closes[0]) / closes[0]) * 100, 2)

    return {
        "ma20": ma20,
        "ma50": ma50,
        "rsi14": rsi14,
        "pct_vs_ma20": pct_vs_ma20,
        "range_20d": {
            "low": round(low_20, 4),
            "high": round(high_20, 4),
            "position_pct": range_position_pct,
        },
        "change_percent_period": period_change,
    }


def classify_strategies(snapshot: dict[str, Any]) -> list[str]:
    """Tag a ticker snapshot with applicable strategy lenses (deterministic)."""
    tags: list[str] = []
    rsi = snapshot.get("rsi14")
    pct_ma = snapshot.get("pct_vs_ma20")
    range_pos = (snapshot.get("range_20d") or {}).get("position_pct")
    change = snapshot.get("change_percent_period")
    price = snapshot.get("price")
    ma20 = snapshot.get("ma20")
    ma50 = snapshot.get("ma50")

    if rsi is not None and pct_ma is not None and rsi < 38 and pct_ma < -4:
        tags.append("pullback")

    if (
        rsi is not None
        and change is not None
        and ma20 is not None
        and price is not None
        and 52 <= rsi <= 78
        and change > 2
        and price > ma20
    ):
        tags.append("momentum")

    if (
        ma20 is not None
        and ma50 is not None
        and price is not None
        and price > ma20
        and ma20 >= ma50 * 0.98
    ):
        tags.append("trend")

    if range_pos is not None and range_pos >= 82:
        tags.append("breakout")

    if (
        range_pos is not None
        and rsi is not None
        and 30 <= range_pos <= 70
        and 38 <= rsi <= 62
    ):
        tags.append("range")

    return tags

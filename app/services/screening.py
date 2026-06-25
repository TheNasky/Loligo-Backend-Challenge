"""Multi-strategy universe screening — not mean-reversion-only."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.indicators import classify_strategies
from app.services.yahoo import fetch_snapshot

DEFAULT_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AMD", "INTC",
    "TSLA", "JPM", "BAC", "V", "MA", "UNH", "JNJ", "PG", "KO", "PEP",
    "WMT", "COST", "HD", "LOW", "NFLX", "DIS", "BA", "CAT", "DE",
    "KLAC", "LRCX", "AVGO",
]

STRATEGY_ORDER = ("momentum", "trend", "breakout", "pullback", "range")


def _compact_row(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": data["ticker"],
        "price": data.get("price"),
        "rsi14": data.get("rsi14"),
        "ma20": data.get("ma20"),
        "ma50": data.get("ma50"),
        "pct_vs_ma20": data.get("pct_vs_ma20"),
        "change_percent_period": data.get("change_percent_period"),
        "range_20d": data.get("range_20d"),
        "strategy_tags": data.get("strategy_tags", []),
    }


def _screen_one(ticker: str) -> dict[str, Any] | None:
    data = fetch_snapshot(ticker)
    if "error" in data:
        return None
    tags = classify_strategies(data)
    if not tags:
        return None
    row = _compact_row(data)
    row["strategy_tags"] = tags
    return row


def _rank_for_strategy(row: dict[str, Any], strategy: str) -> float:
    rsi = row.get("rsi14") or 50
    change = row.get("change_percent_period") or 0
    range_pos = (row.get("range_20d") or {}).get("position_pct") or 50
    pct_ma = row.get("pct_vs_ma20") or 0

    if strategy == "momentum":
        return change + (rsi - 50) * 0.2
    if strategy == "trend":
        return change + max(0.0, pct_ma) * 0.5
    if strategy == "breakout":
        return range_pos
    if strategy == "pullback":
        return max(0.0, 40 - rsi) + max(0.0, -pct_ma)
    if strategy == "range":
        return 100 - abs(range_pos - 50)
    return 0.0


def scan_trading_setups(
    tickers: list[str] | None = None,
    per_strategy: int = 4,
) -> dict[str, Any]:
    """
    Scan liquid stocks and bucket top names by strategy lens.

    Returns separate lists for momentum, trend, breakout, pullback, and range —
    not a single mean-reversion ranking.
    """
    universe = (tickers or DEFAULT_UNIVERSE)[:30]
    per_strategy = max(1, min(per_strategy, 8))

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_screen_one, t): t for t in universe}
        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)

    by_strategy: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATEGY_ORDER}

    for strategy in STRATEGY_ORDER:
        candidates = [r for r in rows if strategy in r.get("strategy_tags", [])]
        candidates.sort(key=lambda r: _rank_for_strategy(r, strategy), reverse=True)
        by_strategy[strategy] = [_compact_row(c) for c in candidates[:per_strategy]]

    return {
        "action": "scan_trading_setups",
        "universe_size": len(universe),
        "tickers_scanned": len(rows),
        "by_strategy": by_strategy,
        "strategies": list(STRATEGY_ORDER),
        "note": (
            "Each bucket uses deterministic rules (RSI, MAs, range, returns). "
            "Present ALL strategy sections — do not focus only on pullback/mean reversion."
        ),
    }

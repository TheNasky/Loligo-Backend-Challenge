"""Build typed UI artifacts from raw tool outputs for the frontend."""

import json
from typing import Any

STRATEGY_LABELS: dict[str, str] = {
    "momentum": "Momentum",
    "trend": "Trend",
    "breakout": "Breakout",
    "pullback": "Pullback",
    "range": "Range",
}


def _parse_output(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _ticker_row(row: dict[str, Any]) -> dict[str, Any]:
    range_20d = row.get("range_20d") or {}
    return {
        "ticker": row.get("ticker"),
        "price": row.get("price"),
        "rsi14": row.get("rsi14"),
        "ma20": row.get("ma20"),
        "ma50": row.get("ma50"),
        "pct_vs_ma20": row.get("pct_vs_ma20"),
        "change_percent_period": row.get("change_percent_period"),
        "range_position_pct": range_20d.get("position_pct"),
        "range_low": range_20d.get("low"),
        "range_high": range_20d.get("high"),
        "strategy_tags": row.get("strategy_tags", []),
    }


def build_artifacts_from_tool_outputs(
    tool_outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert tool JSON into renderable UI blocks (deterministic, not LLM-generated)."""
    artifacts: list[dict[str, Any]] = []

    for entry in tool_outputs:
        name = entry.get("name", "")
        output = _parse_output(entry.get("output"))
        if not output or output.get("error"):
            continue

        if name == "scan_market_setups":
            by_strategy = output.get("by_strategy") or {}
            buckets: list[dict[str, Any]] = []
            for key, label in STRATEGY_LABELS.items():
                picks = by_strategy.get(key) or []
                if not picks:
                    continue
                buckets.append(
                    {
                        "strategy": key,
                        "label": label,
                        "tickers": [_ticker_row(p) for p in picks],
                    }
                )
            if buckets:
                artifacts.append(
                    {
                        "type": "strategy_scan",
                        "universe_size": output.get("universe_size"),
                        "tickers_scanned": output.get("tickers_scanned"),
                        "buckets": buckets,
                    }
                )

        elif name == "get_market_data":
            action = output.get("action")
            if action == "snapshot":
                range_20d = output.get("range_20d") or {}
                sparkline = output.get("sparkline") or output.get("closes") or []
                artifacts.append(
                    {
                        "type": "ticker_snapshot",
                        "ticker": output.get("ticker"),
                        "price": output.get("price"),
                        "currency": output.get("currency", "USD"),
                        "change_percent": output.get("change_percent"),
                        "change_percent_period": output.get("change_percent_period"),
                        "rsi14": output.get("rsi14"),
                        "ma20": output.get("ma20"),
                        "ma50": output.get("ma50"),
                        "pct_vs_ma20": output.get("pct_vs_ma20"),
                        "range_20d": range_20d,
                        "sparkline": sparkline[-30:] if sparkline else [],
                        "strategy_tags": output.get("strategy_tags", []),
                    }
                )
            elif action == "history":
                closes = output.get("closes") or []
                artifacts.append(
                    {
                        "type": "price_chart",
                        "ticker": output.get("ticker"),
                        "closes": closes[-60:],
                        "dates": (output.get("dates") or [])[-60:],
                        "change_percent": output.get("change_percent"),
                    }
                )

        elif name == "get_ticker_news":
            articles = output.get("articles") or []
            if articles:
                artifacts.append(
                    {
                        "type": "news_digest",
                        "ticker": output.get("ticker"),
                        "articles": [
                            {
                                "title": a.get("title"),
                                "publisher": a.get("publisher"),
                                "link": a.get("link"),
                            }
                            for a in articles[:8]
                        ],
                    }
                )

    return artifacts

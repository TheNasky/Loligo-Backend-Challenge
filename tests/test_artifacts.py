from app.services.artifacts import build_artifacts_from_tool_outputs


def test_build_strategy_scan_artifact() -> None:
    outputs = [
        {
            "name": "scan_market_setups",
            "input": {},
            "output": {
                "action": "scan_trading_setups",
                "universe_size": 30,
                "by_strategy": {
                    "momentum": [
                        {
                            "ticker": "NVDA",
                            "price": 500.0,
                            "rsi14": 60.0,
                            "pct_vs_ma20": 5.0,
                            "range_20d": {"position_pct": 70.0},
                        }
                    ],
                    "pullback": [],
                },
            },
        }
    ]
    artifacts = build_artifacts_from_tool_outputs(outputs)
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "strategy_scan"
    assert artifacts[0]["buckets"][0]["strategy"] == "momentum"
def test_build_dual_snapshot_artifacts() -> None:
    outputs = [
        {
            "name": "get_market_data",
            "input": {"ticker": "INTC", "action": "snapshot"},
            "output": {
                "ticker": "INTC",
                "action": "snapshot",
                "price": 130.0,
                "currency": "USD",
                "rsi14": 58.0,
                "ma20": 118.0,
                "range_20d": {"low": 99.0, "high": 140.0, "position_pct": 72.0},
                "sparkline": [120.0, 125.0, 130.0],
                "strategy_tags": ["momentum", "trend"],
            },
        },
        {
            "name": "get_market_data",
            "input": {"ticker": "AMD", "action": "snapshot"},
            "output": {
                "ticker": "AMD",
                "action": "snapshot",
                "price": 517.0,
                "currency": "USD",
                "rsi14": 56.0,
                "ma20": 511.0,
                "range_20d": {"low": 452.0, "high": 551.0, "position_pct": 66.0},
                "sparkline": [480.0, 500.0, 517.0],
                "strategy_tags": ["momentum", "trend", "range"],
            },
        },
    ]
    artifacts = build_artifacts_from_tool_outputs(outputs)
    assert len(artifacts) == 2
    tickers = {a["ticker"] for a in artifacts}
    assert tickers == {"INTC", "AMD"}


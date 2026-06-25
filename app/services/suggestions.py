"""Dynamic welcome-screen suggestion chips from live market data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.services.screening import DEFAULT_UNIVERSE, _rank_for_strategy, _screen_one

SuggestionKind = Literal["overview", "explain", "compare", "news", "ideas"]
Lang = Literal["es", "en"]

POOL_SIZE = 12

SUGGESTION_UNIVERSE = DEFAULT_UNIVERSE[:18]

SECTOR_PEERS: dict[str, list[str]] = {
    "semis": ["NVDA", "AMD", "INTC", "AVGO", "KLAC", "LRCX"],
    "mega": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    "financials": ["JPM", "BAC", "V", "MA"],
}

SECTOR_LABELS: dict[str, dict[Lang, str]] = {
    "semis": {"en": "chip stocks", "es": "semiconductores"},
    "mega": {"en": "big tech", "es": "gran tecnología"},
    "financials": {"en": "banks & payments", "es": "bancos y pagos"},
}

CACHE_TTL = timedelta(minutes=30)

_rows_cache: list[dict[str, Any]] | None = None
_rows_cached_at: datetime | None = None


def _get_scan_rows() -> list[dict[str, Any]]:
    global _rows_cache, _rows_cached_at

    now = datetime.now(UTC)
    if (
        _rows_cache is not None
        and _rows_cached_at is not None
        and now - _rows_cached_at < CACHE_TTL
    ):
        return _rows_cache

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_screen_one, t): t for t in SUGGESTION_UNIVERSE}
        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)

    _rows_cache = rows
    _rows_cached_at = now
    return rows


def _top_for_strategy(rows: list[dict[str, Any]], strategy: str) -> dict[str, Any] | None:
    candidates = [r for r in rows if strategy in r.get("strategy_tags", [])]
    if not candidates:
        return None
    candidates.sort(key=lambda r: _rank_for_strategy(r, strategy), reverse=True)
    return candidates[0]


def _top_n_for_strategy(rows: list[dict[str, Any]], strategy: str, n: int) -> list[dict[str, Any]]:
    candidates = [r for r in rows if strategy in r.get("strategy_tags", [])]
    candidates.sort(key=lambda r: _rank_for_strategy(r, strategy), reverse=True)
    return candidates[:n]


def _peer_pairs(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any], str | None]]:
    by_ticker = {r["ticker"]: r for r in rows}
    pairs: list[tuple[dict[str, Any], dict[str, Any], str | None]] = []

    for sector, peers in SECTOR_PEERS.items():
        present = [by_ticker[t] for t in peers if t in by_ticker]
        if len(present) >= 2:
            present.sort(
                key=lambda r: abs(r.get("change_percent_period") or 0),
                reverse=True,
            )
            pairs.append((present[0], present[1], sector))
            if len(present) >= 3:
                pairs.append((present[0], present[2], sector))

    if len(rows) >= 2 and not pairs:
        ranked = sorted(
            rows,
            key=lambda r: abs(r.get("change_percent_period") or 0),
            reverse=True,
        )
        pairs.append((ranked[0], ranked[1], None))

    return pairs


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _market_pulse(rows: list[dict[str, Any]], lang: Lang) -> dict[str, str]:
    leader = _top_for_strategy(rows, "momentum") or max(
        rows, key=lambda r: abs(r.get("change_percent_period") or 0)
    )
    ticker = leader["ticker"]
    if lang == "es":
        return {
            "kind": "overview",
            "label": "¿Qué se mueve hoy?",
            "message": (
                f"Dame un resumen claro de qué está pasando en el mercado hoy para alguien "
                f"que no es experto. Menciona unos pocos nombres interesantes (vi que {ticker} "
                f"destaca) y explícalo sin jerga técnica."
            ),
        }
    return {
        "kind": "overview",
        "label": "What's moving today?",
        "message": (
            f"Give me a clear, beginner-friendly overview of what's interesting in the "
            f"market today. Mention a few names worth knowing ({ticker} seems active) — "
            f"plain language, no jargon."
        ),
    }


def _big_picture(rows: list[dict[str, Any]], lang: Lang) -> dict[str, str]:
    movers = sorted(
        rows,
        key=lambda r: abs(r.get("change_percent_period") or 0),
        reverse=True,
    )[:3]
    names = ", ".join(r["ticker"] for r in movers)
    if lang == "es":
        return {
            "kind": "overview",
            "label": "El mercado en palabras simples",
            "message": (
                f"Explícame cómo va el mercado últimamente en términos sencillos. "
                f"¿Qué sectores van fuerte o flojos? Nombres con movimiento reciente: {names}. "
                f"Asume que soy principiante."
            ),
        }
    return {
        "kind": "overview",
        "label": "Market in plain English",
        "message": (
            f"Explain how the market has been behaving lately in simple terms. "
            f"Which areas look strong or weak? Recent movers include {names}. "
            f"Assume I'm a casual investor, not a pro."
        ),
    }


def _explain_stock(row: dict[str, Any], lang: Lang, variant: int = 0) -> dict[str, str]:
    ticker = row["ticker"]
    change = _fmt_pct(row.get("change_percent_period"))
    labels_en = [
        f"What's the story with {ticker}?",
        f"Explain {ticker} for a beginner",
        f"Is {ticker} worth a look?",
    ]
    labels_es = [
        f"¿Qué pasa con {ticker}?",
        f"Explícame {ticker} sin tecnicismos",
        f"¿Merece la pena mirar {ticker}?",
    ]
    if lang == "es":
        return {
            "kind": "explain",
            "label": labels_es[variant % len(labels_es)],
            "message": (
                f"Explícame {ticker} en lenguaje sencillo: qué hace la empresa, cómo ha ido "
                f"el precio ({change} reciente) y qué debería saber un inversor casual. "
                f"Sin abrumar con indicadores."
            ),
        }
    return {
        "kind": "explain",
        "label": labels_en[variant % len(labels_en)],
        "message": (
            f"Explain {ticker} in plain English — what the company does, how the stock has "
            f"been moving ({change} recently), and what a casual investor should know. "
            f"Keep it approachable, not a wall of indicators."
        ),
    }


def _teach_one_stock(row: dict[str, Any], lang: Lang) -> dict[str, str]:
    ticker = row["ticker"]
    if lang == "es":
        return {
            "kind": "explain",
            "label": "Enséñame con un solo ejemplo",
            "message": (
                f"Soy nuevo en bolsa. Usa {ticker} como ejemplo y enséñame cómo leer una "
                f"ficha básica: precio, tendencia reciente y noticias — paso a paso y sin presión."
            ),
        }
    return {
        "kind": "explain",
        "label": "Teach me with one example",
        "message": (
            f"I'm new to stocks. Use {ticker} as a worked example and walk me through a "
            f"basic read — price, recent trend, and news — step by step, no pressure."
        ),
    }


def _friendly_compare(
    a: dict[str, Any], b: dict[str, Any], lang: Lang, sector: str | None = None
) -> dict[str, str]:
    ta, tb = a["ticker"], b["ticker"]
    sector_hint = ""
    if sector:
        sector_hint = SECTOR_LABELS.get(sector, {}).get(lang, "")
    if lang == "es":
        label = f"¿{ta} o {tb} — cuál va mejor?"
        if sector_hint:
            label = f"{sector_hint.capitalize()}: ¿{ta} o {tb}?"
        return {
            "kind": "compare",
            "label": label,
            "message": (
                f"Compara {ta} y {tb} de forma sencilla: cuál ha ido mejor ({_fmt_pct(a.get('change_percent_period'))} "
                f"vs {_fmt_pct(b.get('change_percent_period'))}), qué cuenta la historia de cada una "
                f"y cuál parece más sólida ahora. Para alguien que no es experto."
            ),
        }
    label = f"{ta} or {tb} — which looks stronger?"
    if sector_hint:
        label = f"{sector_hint.capitalize()}: {ta} or {tb}?"
    return {
        "kind": "compare",
        "label": label,
        "message": (
            f"Compare {ta} and {tb} in simple terms — who's done better lately "
            f"({_fmt_pct(a.get('change_percent_period'))} vs {_fmt_pct(b.get('change_percent_period'))}), "
            f"what's the story behind each, and which looks healthier right now. "
            f"Keep it beginner-friendly."
        ),
    }


def _news_roundup(row: dict[str, Any], lang: Lang) -> dict[str, str]:
    ticker = row["ticker"]
    if lang == "es":
        return {
            "kind": "news",
            "label": "Noticias que importan hoy",
            "message": (
                f"Resume las noticias recientes que más pueden mover el mercado o nombres "
                f"como {ticker}. Explícalo para alguien que no sigue la prensa financiera a diario."
            ),
        }
    return {
        "kind": "news",
        "label": "Headlines worth knowing",
        "message": (
            f"Summarize the news that's actually moving stocks today — including anything "
            f"around {ticker} if relevant. Explain it for someone who doesn't read "
            f"financial press every day."
        ),
    }


def _stocks_to_watch(rows: list[dict[str, Any]], lang: Lang) -> dict[str, str]:
    picks = _top_n_for_strategy(rows, "momentum", 3) or sorted(
        rows,
        key=lambda r: abs(r.get("change_percent_period") or 0),
        reverse=True,
    )[:3]
    names = ", ".join(r["ticker"] for r in picks)
    if lang == "es":
        return {
            "kind": "ideas",
            "label": "Nombres para tener en el radar",
            "message": (
                f"Sugiere 3 acciones interesantes para mirar esta semana y por qué — "
                f"en lenguaje sencillo. Puedes empezar por {names} si encajan."
            ),
        }
    return {
        "kind": "ideas",
        "label": "Stocks to keep on your radar",
        "message": (
            f"Suggest a few stocks worth watching this week and why — in plain language. "
            f"You can start with names like {names} if they fit."
        ),
    }


def _caution_check(row: dict[str, Any], lang: Lang) -> dict[str, str]:
    ticker = row["ticker"]
    if lang == "es":
        return {
            "kind": "ideas",
            "label": "¿Algo que deba tener cuidado?",
            "message": (
                f"¿Hay algo en el mercado que parezca demasiado extendido o arriesgado ahora? "
                f"Menciona {ticker} si aplica. Quiero una lectura honesta y fácil de entender."
            ),
        }
    return {
        "kind": "ideas",
        "label": "Anything to be careful about?",
        "message": (
            f"Is anything in the market looking stretched or risky right now? "
            f"Mention {ticker} if it applies. Give me an honest, easy-to-understand take."
        ),
    }


def _sector_snapshot(sector: str, rows: list[dict[str, Any]], lang: Lang) -> dict[str, str]:
    peers = SECTOR_PEERS.get(sector, [])
    present = [r for r in rows if r["ticker"] in peers]
    names = ", ".join(r["ticker"] for r in present[:4]) or "—"
    sector_label = SECTOR_LABELS.get(sector, {}).get(lang, sector)
    if lang == "es":
        return {
            "kind": "overview",
            "label": f"Panorama de {sector_label}",
            "message": (
                f"Dame una visión general de {sector_label} para un principiante. "
                f"¿Cómo van {names}? Sin estrategias complicadas, solo contexto útil."
            ),
        }
    return {
        "kind": "overview",
        "label": f"{sector_label.capitalize()} — quick snapshot",
        "message": (
            f"Give me a beginner-friendly snapshot of {sector_label}. "
            f"How are names like {names} doing? Useful context, not complicated strategies."
        ),
    }


def _append_unique(pool: list[dict[str, str]], item: dict[str, str]) -> None:
    labels = {p["label"] for p in pool}
    if item["label"] not in labels and len(pool) < POOL_SIZE:
        pool.append(item)


def _build_pool(rows: list[dict[str, Any]], lang: Lang) -> list[dict[str, str]]:
    pool: list[dict[str, str]] = []

    _append_unique(pool, _market_pulse(rows, lang))
    _append_unique(pool, _big_picture(rows, lang))
    _append_unique(pool, _stocks_to_watch(rows, lang))
    _append_unique(pool, _news_roundup(
        _top_for_strategy(rows, "momentum") or rows[0], lang
    ))

    for i, row in enumerate(_top_n_for_strategy(rows, "trend", 3)):
        _append_unique(pool, _explain_stock(row, lang, variant=i))

    leader = _top_for_strategy(rows, "momentum") or rows[0]
    _append_unique(pool, _teach_one_stock(leader, lang))

    for a, b, sector in _peer_pairs(rows)[:3]:
        _append_unique(pool, _friendly_compare(a, b, lang, sector))

    pullback = _top_for_strategy(rows, "pullback")
    if pullback:
        _append_unique(pool, _caution_check(pullback, lang))

    for sector in ("semis", "mega", "financials"):
        if len(pool) >= POOL_SIZE:
            break
        _append_unique(pool, _sector_snapshot(sector, rows, lang))

    # Fill remaining slots with explain picks on active names
    for i, row in enumerate(
        sorted(rows, key=lambda r: abs(r.get("change_percent_period") or 0), reverse=True)
    ):
        if len(pool) >= POOL_SIZE:
            break
        _append_unique(pool, _explain_stock(row, lang, variant=i + 1))

    return pool[:POOL_SIZE]


def build_suggestions(lang: str = "es") -> dict[str, Any]:
    """Build a pool of localized suggestion chips (client picks 3 to display)."""
    locale: Lang = "en" if lang == "en" else "es"
    rows = _get_scan_rows()

    if not rows:
        return _fallback_payload(locale)

    generated_at = datetime.now(UTC)
    suggestions = _build_pool(rows, locale)
    if len(suggestions) < 3:
        suggestions = _fallback_payload(locale)["suggestions"]

    return {
        "generated_at": generated_at.isoformat(),
        "expires_at": (generated_at + CACHE_TTL).isoformat(),
        "source": "yahoo_finance",
        "suggestions": suggestions,
    }


def _fallback_payload(lang: Lang) -> dict[str, Any]:
    generated_at = datetime.now(UTC)
    if lang == "es":
        suggestions = [
            {
                "kind": "overview",
                "label": "¿Qué se mueve hoy?",
                "message": "Dame un resumen claro del mercado hoy para alguien que no es experto. Sin jerga.",
            },
            {
                "kind": "overview",
                "label": "El mercado en palabras simples",
                "message": "Explícame cómo va el mercado últimamente en términos sencillos. Asume que soy principiante.",
            },
            {
                "kind": "explain",
                "label": "¿Qué pasa con AAPL?",
                "message": "Explícame Apple en lenguaje sencillo: qué hace, cómo va el precio y qué debería saber un inversor casual.",
            },
            {
                "kind": "compare",
                "label": "Semiconductores: ¿NVDA o AMD?",
                "message": "Compara NVDA y AMD de forma sencilla — cuál va mejor, qué cuenta la historia de cada una y cuál parece más sólida.",
            },
            {
                "kind": "news",
                "label": "Noticias que importan hoy",
                "message": "Resume las noticias que más pueden mover el mercado hoy. Para alguien que no sigue la prensa financiera a diario.",
            },
            {
                "kind": "ideas",
                "label": "Nombres para tener en el radar",
                "message": "Sugiere 3 acciones interesantes para mirar esta semana y por qué — en lenguaje sencillo.",
            },
            {
                "kind": "explain",
                "label": "Explícame MSFT sin tecnicismos",
                "message": "Explícame Microsoft en lenguaje sencillo — negocio, precio reciente y qué debería saber un inversor casual.",
            },
            {
                "kind": "ideas",
                "label": "¿Algo que deba tener cuidado?",
                "message": "¿Hay algo en el mercado que parezca demasiado extendido o arriesgado? Lectura honesta y fácil de entender.",
            },
            {
                "kind": "overview",
                "label": "Panorama de gran tecnología",
                "message": "Visión general de gran tecnología para un principiante. ¿Cómo van AAPL, MSFT, GOOGL y AMZN?",
            },
            {
                "kind": "explain",
                "label": "Enséñame con un solo ejemplo",
                "message": "Soy nuevo en bolsa. Usa un nombre conocido como ejemplo y enséñame a leer una ficha básica paso a paso.",
            },
            {
                "kind": "compare",
                "label": "Bancos y pagos: ¿JPM o BAC?",
                "message": "Compara JPM y BAC de forma sencilla para alguien que no es experto.",
            },
            {
                "kind": "ideas",
                "label": "Ideas para empezar a mirar",
                "message": "Si apenas empiezo, ¿qué 2–3 nombres conocidos merecen una primera mirada y por qué?",
            },
        ]
    else:
        suggestions = [
            {
                "kind": "overview",
                "label": "What's moving today?",
                "message": "Give me a clear, beginner-friendly overview of what's interesting in the market today. Plain language, no jargon.",
            },
            {
                "kind": "overview",
                "label": "Market in plain English",
                "message": "Explain how the market has been behaving lately in simple terms. Assume I'm a casual investor.",
            },
            {
                "kind": "explain",
                "label": "What's the story with AAPL?",
                "message": "Explain Apple in plain English — what it does, how the stock has been moving, and what a casual investor should know.",
            },
            {
                "kind": "compare",
                "label": "Chip stocks: NVDA or AMD?",
                "message": "Compare NVDA and AMD in simple terms — who's done better, what's the story behind each, and which looks healthier.",
            },
            {
                "kind": "news",
                "label": "Headlines worth knowing",
                "message": "Summarize the news that's actually moving stocks today. For someone who doesn't read financial press every day.",
            },
            {
                "kind": "ideas",
                "label": "Stocks to keep on your radar",
                "message": "Suggest a few stocks worth watching this week and why — in plain language.",
            },
            {
                "kind": "explain",
                "label": "Explain MSFT for a beginner",
                "message": "Explain Microsoft in plain English — business, recent price action, and what a casual investor should know.",
            },
            {
                "kind": "ideas",
                "label": "Anything to be careful about?",
                "message": "Is anything in the market looking stretched or risky right now? Honest, easy-to-understand take.",
            },
            {
                "kind": "overview",
                "label": "Big tech — quick snapshot",
                "message": "Beginner-friendly snapshot of big tech. How are AAPL, MSFT, GOOGL, and AMZN doing?",
            },
            {
                "kind": "explain",
                "label": "Teach me with one example",
                "message": "I'm new to stocks. Use a well-known name as a worked example and walk me through a basic read step by step.",
            },
            {
                "kind": "compare",
                "label": "Banks & payments: JPM or BAC?",
                "message": "Compare JPM and BAC in simple terms for someone who isn't an expert.",
            },
            {
                "kind": "ideas",
                "label": "Ideas for getting started",
                "message": "If I'm just getting started, what 2–3 familiar names are worth a first look and why?",
            },
        ]

    return {
        "generated_at": generated_at.isoformat(),
        "expires_at": (generated_at + timedelta(minutes=15)).isoformat(),
        "source": "fallback",
        "suggestions": suggestions,
    }


def clear_suggestions_cache() -> None:
    """Test helper — reset in-memory scan cache."""
    global _rows_cache, _rows_cached_at
    _rows_cache = None
    _rows_cached_at = None

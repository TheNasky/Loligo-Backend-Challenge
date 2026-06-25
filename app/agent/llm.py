"""LLM factory — OpenAI (default) or any OpenAI-compatible API (e.g. Groq)."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings


@lru_cache
def get_llm(settings: Settings | None = None) -> ChatOpenAI:
    cfg = settings or get_settings()
    return ChatOpenAI(
        model=cfg.llm_model,
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        temperature=0.2,
    )

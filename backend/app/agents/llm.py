"""LLM factory: GPT-4o-mini primary, Groq Llama fallback.

Both providers expose an OpenAI-compatible chat completions API, so we use a
single `langchain_openai.ChatOpenAI` instance per provider and switch based on
availability.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logging import logger

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _try_openai() -> ChatOpenAI | None:
    """Build a ChatOpenAI client; honours OPENAI_BASE_URL for gateway proxies."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        kwargs = dict(
            model=settings.primary_llm_model,
            api_key=settings.openai_api_key,
            temperature=0.2,
            timeout=30,
            max_retries=3,   # allows automatic retry on Groq 429 (rate-limit)
        )
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        llm = ChatOpenAI(**kwargs)
        target = settings.openai_base_url or "api.openai.com"
        logger.info("LLM ready: openai:{} via {}", settings.primary_llm_model, target)
        return llm
    except Exception as exc:  # pragma: no cover
        logger.warning("OpenAI LLM init failed: {}", exc)
        return None


def _try_groq() -> ChatOpenAI | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    try:
        llm = ChatOpenAI(
            model=settings.fallback_llm_model,
            api_key=settings.groq_api_key,
            base_url=GROQ_BASE_URL,
            temperature=0.2,
            timeout=30,
            max_retries=3,   # allows automatic retry on Groq 429 (rate-limit)
        )
        logger.info("LLM ready: groq:{}", settings.fallback_llm_model)
        return llm
    except Exception as exc:  # pragma: no cover
        logger.warning("Groq LLM init failed: {}", exc)
        return None


@lru_cache
def get_llm() -> ChatOpenAI:
    """Return the best available LLM client. Raises if none configured."""
    llm = _try_openai() or _try_groq()
    if llm is None:
        raise RuntimeError(
            "No LLM available. Set OPENAI_API_KEY or GROQ_API_KEY in your .env."
        )
    return llm


__all__ = ["get_llm"]

"""LangSmith tracing setup.

LangSmith is environment-driven: setting `LANGSMITH_TRACING=true` and a valid
`LANGSMITH_API_KEY` is sufficient — LangChain/LangGraph pick them up automatically.

This module just normalises the env vars to the names LangChain reads, and
emits a single log line so it's obvious whether tracing is active.
"""
from __future__ import annotations

import os

from app.core.config import get_settings
from app.core.logging import logger


def setup_tracing() -> None:
    """Apply env vars LangChain reads (LANGCHAIN_*) from our settings."""
    settings = get_settings()
    if settings.langsmith_api_key and settings.langsmith_tracing:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        logger.info("LangSmith tracing enabled | project={}", settings.langsmith_project)
    else:
        # ensure tracing is off if not explicitly enabled
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        logger.info("LangSmith tracing disabled.")


__all__ = ["setup_tracing"]

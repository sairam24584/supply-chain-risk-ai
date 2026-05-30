"""Embeddings provider with OpenAI primary + local SentenceTransformer fallback.

Exposes a single `get_embedder()` factory that returns a callable
`embed(texts: list[str]) -> list[list[float]]`.
"""
from __future__ import annotations

from typing import Callable, Protocol

from app.core.config import get_settings
from app.core.logging import logger


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Uses any OpenAI-compatible embeddings API (official OpenAI or a gateway)."""

    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        from openai import OpenAI  # local import keeps cold-start light

        suffix = f" via {base_url}" if base_url else ""
        self.name = f"openai:{model}{suffix}"
        self.model = model
        # Only pass base_url when set — keeps default behaviour for stock OpenAI.
        self._client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # OpenAI batches up to 2048 inputs; our corpus is small, single call is fine.
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]


class LocalEmbedder:
    """Local SentenceTransformer fallback (no network needed)."""

    def __init__(self, model: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = f"local:{model}"
        self._model = SentenceTransformer(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return vectors.tolist()


def get_embedder(force_local: bool = False) -> Embedder:
    """Pick the best available embedder. Falls back to local if OpenAI is unavailable."""
    settings = get_settings()
    if not force_local and settings.openai_api_key:
        try:
            embedder = OpenAIEmbedder(
                settings.embedding_model,
                settings.openai_api_key,
                base_url=settings.openai_base_url or None,
            )
            # cheap smoke test on first use happens lazily; just log selection here
            logger.info("Using embedder: {}", embedder.name)
            return embedder
        except Exception as exc:  # pragma: no cover - import / init failure
            logger.warning("OpenAI embedder unavailable ({}); falling back to local.", exc)

    embedder = LocalEmbedder(settings.fallback_embedding_model)
    logger.info("Using embedder: {}", embedder.name)
    return embedder


__all__ = ["Embedder", "OpenAIEmbedder", "LocalEmbedder", "get_embedder"]

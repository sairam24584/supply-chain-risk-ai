"""Cross-encoder reranker (lazy-loaded).

Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` — a small, CPU-friendly model that's
the standard choice for hybrid-retrieval reranking. Gracefully no-ops if the
model cannot be loaded (e.g. offline or missing dep).
"""
from __future__ import annotations

import os
from typing import Any

from app.core.logging import logger

_DISABLED = os.getenv("DISABLE_RERANKER", "").lower() in ("1", "true", "yes")

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None  # lazy

    def _load(self) -> None:
        if self._model is not None:
            return
        if _DISABLED:
            logger.info("Reranker disabled via DISABLE_RERANKER env var.")
            self._model = False
            return
        try:
            from sentence_transformers import CrossEncoder  # heavy import

            self._model = CrossEncoder(self.model_name)
            logger.info("Reranker loaded: {}", self.model_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Reranker unavailable ({}); falling back to identity.", exc)
            self._model = False  # sentinel meaning "give up"

    def rerank(
        self,
        query: str,
        hits: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Rescore `hits` by query relevance. Adds `rerank_score`. Stable on failure."""
        if not hits:
            return hits
        self._load()
        if not self._model:  # fallback: leave order untouched
            return hits[: top_k or len(hits)]

        pairs = [(query, h["text"]) for h in hits]
        scores = self._model.predict(pairs).tolist()
        for h, s in zip(hits, scores):
            h["rerank_score"] = float(s)
        hits.sort(key=lambda h: h["rerank_score"], reverse=True)
        return hits[: top_k or len(hits)]


__all__ = ["CrossEncoderReranker", "DEFAULT_MODEL"]

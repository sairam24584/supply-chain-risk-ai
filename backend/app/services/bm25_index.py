"""In-memory BM25 keyword index over incident records.

The corpus is small (~100 docs) so we rebuild on each app startup from the CSV.
If the corpus grows large, persist `BM25Okapi` state to disk and load it lazily.
"""
from __future__ import annotations

import re
from typing import Any

from rank_bm25 import BM25Okapi

from app.services.data_loader import IncidentRecord

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Index:
    def __init__(self, records: list[IncidentRecord]) -> None:
        self._records = records
        self._tokens = [_tokenize(r.text) for r in records]
        self._bm25 = BM25Okapi(self._tokens) if self._tokens else None

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return top-`top_k` records by BM25 score, optionally filtered by metadata.

        Filtering is applied *after* scoring on the assumption that the corpus is
        small. For large corpora, pre-filter then rescore.
        """
        if self._bm25 is None or not query.strip():
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        # zip scores with records, optionally filter, sort desc, take top_k.
        scored = []
        for rec, score in zip(self._records, scores):
            if where and not _matches(rec.metadata, where):
                continue
            scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits: list[dict[str, Any]] = []
        for score, rec in scored[:top_k]:
            hits.append(
                {
                    "id": rec.doc_id,
                    "text": rec.text,
                    "metadata": rec.metadata,
                    "bm25_score": float(score),
                }
            )
        return hits


def _matches(meta: dict[str, Any], where: dict[str, Any]) -> bool:
    """Minimal Chroma-compatible filter matcher (equality only)."""
    for k, v in where.items():
        if meta.get(k) != v:
            return False
    return True


__all__ = ["BM25Index"]

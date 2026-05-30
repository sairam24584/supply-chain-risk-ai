"""Semantic cache — layered on top of exact-match QueryCache.

If an incoming question doesn't match exactly but its embedding is sufficiently
close (cosine ≥ threshold) to a previously cached query, we return that
response. Avoids re-running the multi-agent pipeline on paraphrases.

Uses the same embedder as ingest so no extra model load is incurred.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any

from app.core.logging import logger
from app.services.embeddings import get_embedder

DEFAULT_TTL_SECONDS = 600
DEFAULT_MAX_ENTRIES = 100
DEFAULT_THRESHOLD = 0.93


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


class SemanticCache:
    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._threshold = threshold
        # list of dicts: {query, embedding, value, ts}
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._embedder = None

    def _ensure_embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def get(self, query: str) -> tuple[Any | None, float | None, dict | None]:
        """Return (value, cached_at_ts, match_info) or (None, None, None)."""
        try:
            emb = self._ensure_embedder().embed([query])[0]
        except Exception as exc:
            logger.warning("Semantic cache embed failed; skipping: {}", exc)
            self._misses += 1
            return None, None, None

        now = time.time()
        best, best_sim = None, 0.0
        with self._lock:
            for e in self._entries:
                if now - e["ts"] > self._ttl:
                    continue
                sim = _cosine(emb, e["embedding"])
                if sim > best_sim:
                    best, best_sim = e, sim
            # prune expired
            self._entries = [e for e in self._entries if now - e["ts"] <= self._ttl]

        if best and best_sim >= self._threshold:
            self._hits += 1
            return (
                best["value"],
                best["ts"],
                {"matched_query": best["query"], "similarity": round(best_sim, 4)},
            )
        self._misses += 1
        return None, None, None

    def set(self, query: str, value: Any) -> None:
        try:
            emb = self._ensure_embedder().embed([query])[0]
        except Exception as exc:
            logger.warning("Semantic cache set failed; skipping: {}", exc)
            return
        now = time.time()
        with self._lock:
            if len(self._entries) >= self._max:
                self._entries.sort(key=lambda e: e["ts"])
                self._entries = self._entries[1:]
            self._entries.append({
                "query": query,
                "embedding": emb,
                "value": value,
                "ts": now,
            })

    def clear(self) -> int:
        with self._lock:
            n = len(self._entries)
            self._entries.clear()
            self._hits = 0
            self._misses = 0
            return n

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "entries": len(self._entries),
            "max_entries": self._max,
            "ttl_seconds": self._ttl,
            "threshold": self._threshold,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total else 0.0,
        }


_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


__all__ = ["SemanticCache", "get_semantic_cache"]

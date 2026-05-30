"""Query-result cache.

Stores the full `QueryResponse` for an identical (query, top_k, filters) tuple
for `ttl_seconds`. Repeat questions are served instantly without re-running the
4 LLM calls + retrieval + reranker.

Design choices:
  * Exact-match key (normalised whitespace + case + filter ordering).
    Semantic cache (embedding-similarity hit) is a future enhancement —
    we'd compute the query embedding, look up the nearest cached entry,
    and accept if cosine ≥ ~0.93.
  * TTL is short (default 10 min) because the underlying dataset is mutable
    and we don't want stale recommendations after re-ingest.
  * In-memory only. For multi-process deployments switch to Redis.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

DEFAULT_TTL_SECONDS = 600
DEFAULT_MAX_ENTRIES = 200


class QueryCache:
    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ---------- key ----------
    @staticmethod
    def _key(query: str, top_k: int, filters: dict[str, Any] | None) -> str:
        norm = " ".join((query or "").lower().split())
        filt = json.dumps(filters or {}, sort_keys=True, default=str)
        raw = f"{norm}|{top_k}|{filt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ---------- core ops ----------
    def get(
        self, query: str, top_k: int, filters: dict[str, Any] | None
    ) -> tuple[Any | None, float | None]:
        """Return (value, cached_at_ts) or (None, None)."""
        k = self._key(query, top_k, filters)
        now = time.time()
        with self._lock:
            entry = self._store.get(k)
            if entry is None:
                self._misses += 1
                return None, None
            ts, val = entry
            if now - ts > self._ttl:
                del self._store[k]
                self._misses += 1
                return None, None
            self._hits += 1
            return val, ts

    def set(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None,
        value: Any,
    ) -> None:
        k = self._key(query, top_k, filters)
        now = time.time()
        with self._lock:
            # naive LRU-ish eviction: drop oldest when full
            if len(self._store) >= self._max:
                oldest_k = min(self._store, key=lambda x: self._store[x][0])
                self._store.pop(oldest_k, None)
            self._store[k] = (now, value)

    def clear(self) -> int:
        with self._lock:
            n = len(self._store)
            self._store.clear()
            self._hits = 0
            self._misses = 0
            return n

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "max_entries": self._max,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total else 0.0,
            }


# Process-wide singleton
_cache: QueryCache | None = None


def get_query_cache() -> QueryCache:
    global _cache
    if _cache is None:
        _cache = QueryCache()
    return _cache


__all__ = ["QueryCache", "get_query_cache"]

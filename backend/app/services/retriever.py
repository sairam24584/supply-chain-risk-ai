"""Hybrid retrieval orchestrator.

Pipeline:  query
              ├─> Chroma semantic search  (top N)
              └─> BM25 keyword search     (top N)
                          │
                          ▼
                Reciprocal Rank Fusion (RRF)
                          │
                          ▼
              Cross-encoder reranker (optional)
                          │
                          ▼
                       top_k hits
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.logging import logger
from app.services.bm25_index import BM25Index
from app.services.data_loader import build_incident_records, load_dataframe
from app.services.reranker import CrossEncoderReranker
from app.services.vector_store import VectorStore, get_vector_store

# Lazy import to avoid circular deps at module load time
def _apply_feedback(hits):
    try:
        from app.services.feedback import apply_feedback_boost
        return apply_feedback_boost(hits)
    except Exception:
        return hits

# RRF constant — k=60 is the standard tuned default from the original RRF paper.
RRF_K = 60
DEFAULT_FETCH_K = 20  # how many to pull from each retriever before fusion


def _rrf_fuse(
    semantic_hits: list[dict[str, Any]],
    bm25_hits: list[dict[str, Any]],
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Combine two ranked hit lists with Reciprocal Rank Fusion."""
    pool: dict[str, dict[str, Any]] = {}

    def _add(hits: list[dict[str, Any]], source: str) -> None:
        for rank, hit in enumerate(hits):
            doc_id = hit["id"]
            if doc_id not in pool:
                pool[doc_id] = {
                    "id": doc_id,
                    "text": hit["text"],
                    "metadata": hit["metadata"],
                    "rrf_score": 0.0,
                    "sources": [],
                }
            pool[doc_id]["rrf_score"] += 1.0 / (k + rank + 1)
            pool[doc_id]["sources"].append(source)
            # carry through individual scores for transparency
            for sk in ("distance", "bm25_score"):
                if sk in hit and sk not in pool[doc_id]:
                    pool[doc_id][sk] = hit[sk]

    _add(semantic_hits, "semantic")
    _add(bm25_hits, "bm25")

    fused = sorted(pool.values(), key=lambda h: h["rrf_score"], reverse=True)
    return fused


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        bm25: BM25Index,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        self._vs = vector_store
        self._bm25 = bm25
        self._reranker = reranker

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
        rerank: bool = True,
        fetch_k: int = DEFAULT_FETCH_K,
    ) -> list[dict[str, Any]]:
        semantic = self._vs.similarity_search(query, top_k=fetch_k, where=where)
        keyword = self._bm25.search(query, top_k=fetch_k, where=where)
        fused = _rrf_fuse(semantic, keyword)
        # Apply feedback score boost/penalty before reranking
        fused = _apply_feedback(fused)
        if rerank and self._reranker:
            fused = self._reranker.rerank(query, fused, top_k=top_k)
        else:
            fused = fused[:top_k]
        return fused


@lru_cache
def get_retriever() -> HybridRetriever:
    """Process-wide singleton. Rebuilds BM25 from CSV; Chroma is already persistent."""
    settings = get_settings()
    df = load_dataframe(settings.data_csv_path)
    records = build_incident_records(df)
    bm25 = BM25Index(records)
    vs = get_vector_store()
    reranker = CrossEncoderReranker()
    logger.info(
        "HybridRetriever ready | bm25_docs={} | vector_docs={}",
        len(records),
        vs.count(),
    )
    return HybridRetriever(vector_store=vs, bm25=bm25, reranker=reranker)


__all__ = ["HybridRetriever", "get_retriever", "RRF_K", "DEFAULT_FETCH_K"]

"""Hybrid retrieval endpoint — diagnostic/debug surface for the RAG layer.

The agent pipeline (Step 4) will call `get_retriever()` directly. This HTTP
endpoint lets us sanity-check retrieval quality from the frontend or curl.
"""
from fastapi import APIRouter

from app.models.schemas import RetrievedHit, RetrieveRequest, RetrieveResponse
from app.services.retriever import get_retriever

router = APIRouter(prefix="/api", tags=["retrieval"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(payload: RetrieveRequest) -> RetrieveResponse:
    retriever = get_retriever()
    raw_hits = retriever.retrieve(
        query=payload.query,
        top_k=payload.top_k,
        where=payload.filters,
        rerank=payload.rerank,
    )
    hits = [
        RetrievedHit(
            id=h["id"],
            text=h["text"],
            metadata=h["metadata"],
            rrf_score=h.get("rrf_score"),
            rerank_score=h.get("rerank_score"),
            sources=h.get("sources", []),
        )
        for h in raw_hits
    ]
    return RetrieveResponse(query=payload.query, hits=hits)

"""Feedback loop endpoint — thumbs up/down on query results."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.services.feedback import get_feedback_stats, record_feedback

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    vote: int = Field(..., description="+1 for thumbs up, -1 for thumbs down")
    doc_id: str | None = Field(default=None, description="Source document ID (optional)")
    session_id: str | None = Field(default=None)

    @field_validator("vote")
    @classmethod
    def vote_must_be_binary(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("vote must be +1 or -1")
        return v


@router.post("")
async def submit_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    """Record a thumbs-up (+1) or thumbs-down (-1) for a query result."""
    try:
        return record_feedback(
            query=payload.query,
            vote=payload.vote,
            doc_id=payload.doc_id,
            session_id=payload.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/stats")
async def feedback_stats() -> dict[str, Any]:
    """Aggregate feedback statistics and top-rated documents."""
    return get_feedback_stats()

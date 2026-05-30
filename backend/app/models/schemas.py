"""Pydantic request / response schemas shared across routes."""
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "supply-chain-risk-ai"
    version: str = "0.1.0"


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] | None = Field(default=None, description="Optional metadata filters")
    thread_id: str | None = Field(
        default=None,
        description="Conversation thread id — same id retains agent memory across calls.",
    )
    use_cache: bool = Field(default=True, description="Whether to consult the query result cache.")


class AgentFindings(BaseModel):
    supplier: str | None = None
    shipment: str | None = None
    inventory: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = []
    risk_score: float | None = None
    agents_invoked: list[str] = []
    findings: AgentFindings = Field(default_factory=AgentFindings)
    escalations: list[dict[str, Any]] = []
    guardrail_violations: list[str] = []
    # Structured artefacts (Phase 1.1+)
    recommendation_plan: dict[str, Any] | None = None
    judge_verdict: dict[str, Any] | None = None
    final_report: dict[str, Any] | None = None
    agent_findings: dict[str, Any] = Field(default_factory=dict)
    # Cache / memory metadata
    cache_hit: bool = False
    cache_type: str | None = None   # "exact" | "semantic" | None
    cache_match: dict[str, Any] | None = None
    cached_at: float | None = None
    thread_id: str | None = None
    # Query preprocessing
    query_rewritten: str | None = None
    intent: str | None = None
    intent_confidence: float | None = None
    # Supervisor + retry trail
    supervisor_plan: dict[str, Any] | None = None
    attempts: int = 1
    judge_scores: list[float] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] | None = Field(default=None)
    rerank: bool = Field(default=True)


class RetrievedHit(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any]
    rrf_score: float | None = None
    rerank_score: float | None = None
    sources: list[str] = []


class RetrieveResponse(BaseModel):
    query: str
    hits: list[RetrievedHit]

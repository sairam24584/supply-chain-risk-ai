"""Pydantic schemas the LLM is forced to emit via `llm.with_structured_output(...)`."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SeverityLevel = Literal["low", "medium", "high"]


class AgentFinding(BaseModel):
    finding: str = Field(..., description="One concrete paragraph. Cite suppliers, SKUs, routes, locations from context.")
    severity: SeverityLevel = Field(..., description="Severity of the issue in this domain lens.")
    escalate: bool = Field(..., description="True if other agents should treat this as urgent.")
    escalation_reason: str = Field(default="", description="One-line reason; empty when escalate=false.")
    entities_referenced: list[str] = Field(default_factory=list, description="Entity names cited in the finding.")
    citations: list[str] = Field(
        default_factory=list,
        description="Source identifiers (SKU IDs, source_file names) backing the finding.",
    )


class MitigationAction(BaseModel):
    title: str = Field(
        ...,
        description=(
            "Short imperative action title, <= 12 words. "
            "Must name the specific supplier, SKU, carrier, or route — "
            "never generic like 'Mitigate risk at Supplier X'. "
            "Example: 'Audit Supplier 1 SKU4 defect root cause within 2 weeks'."
        ),
    )
    owner_role: str = Field(..., description="Owner role: 'Procurement Lead', 'Inventory Manager', etc.")
    timeframe_days: int = Field(..., ge=1, le=180, description="Target completion in days.")
    driver: str = Field(..., description="Which agent finding(s) drove this action.")
    priority: int = Field(..., ge=1, le=5, description="1 = highest priority, 5 = lowest.")


class RecommendationPlan(BaseModel):
    executive_summary: str = Field(
        ...,
        description=(
            "2-3 sentences that directly answer the user's question using specific data from the findings. "
            "DO NOT repeat the agent findings verbatim -- synthesise across agents. "
            "Lead with the highest-risk entity (highest defect rate / longest delay / lowest stock). "
            "Name actual suppliers, SKUs, defect rates, carriers, or stock levels. "
            "End with the overall risk implication -- no generic advice. "
            "Example: 'Supplier 1 is the top quality risk with a 3.15% defect rate on SKU4 "
            "(above the 3% severe threshold), followed by Supplier 2 at 2.96% on SKU44. "
            "Concentrated failed inspections at Supplier 2 compound the risk, pushing overall "
            "network quality risk to 8/10.'"
        ),
    )
    actions: list[MitigationAction] = Field(..., min_length=1, max_length=5)
    risk_score: float = Field(..., ge=0.0, le=10.0)
    risk_score_justification: str
    reasoning_trail: str


class JudgeVerdict(BaseModel):
    actionable: bool
    grounded: bool
    prioritised: bool
    score_justified: bool
    citations_valid: bool = Field(default=True, description="Citations exist in retrieved context.")
    overall_quality: float = Field(..., ge=0.0, le=1.0)
    rationale: str


class SupervisorPlan(BaseModel):
    """Supervisor's routing decision for an incoming query."""
    needs_retrieval: bool = Field(default=True, description="False only if memory thread is sufficient.")
    run_supplier: bool = Field(default=True)
    run_shipment: bool = Field(default=True)
    run_inventory: bool = Field(default=True)
    needs_report: bool = Field(default=True, description="If false, skip Report Generation Agent.")
    rationale: str = Field(..., description="2-3 sentence rationale for the routing.")


class FinalReport(BaseModel):
    """Output of the Report Generation Agent -- polished, citation-grounded narrative."""
    title: str
    headline: str = Field(..., description="One-sentence headline summarizing the situation.")
    body: str = Field(..., description="Full markdown-formatted report. 4-8 short paragraphs.")
    cited_entities: list[str] = Field(default_factory=list, description="All suppliers/SKUs/routes mentioned.")
    next_steps: list[str] = Field(default_factory=list, description="3-5 next-step bullets, plain text.")


__all__ = [
    "SeverityLevel", "AgentFinding", "MitigationAction", "RecommendationPlan",
    "JudgeVerdict", "SupervisorPlan", "FinalReport",
]

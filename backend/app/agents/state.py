"""Shared graph state passed between agents."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    # --- inputs ---
    query: str
    filters: dict[str, Any] | None
    top_k: int

    # --- query preprocessing ---
    query_rewritten: str
    intent: str
    intent_confidence: float
    preprocessing_notes: list[str]

    # --- supervisor routing ---
    supervisor_plan: dict[str, Any] | None

    # --- retrieval ---
    retrieved_hits: list[dict[str, Any]]
    compressed_hits: list[dict[str, Any]]

    # --- analytics snapshots ---
    supplier_analytics: dict[str, Any] | None
    shipment_analytics: dict[str, Any] | None
    inventory_analytics: dict[str, Any] | None
    cross_signals: dict[str, Any] | None

    # --- per-specialist findings (structured) ---
    supplier_finding: dict[str, Any] | None
    shipment_finding: dict[str, Any] | None
    inventory_finding: dict[str, Any] | None

    # --- A2A escalation channel ---
    escalations: Annotated[list[dict[str, Any]], operator.add]
    agents_invoked: Annotated[list[str], operator.add]

    # --- synthesis ---
    recommendation_plan: dict[str, Any] | None
    judge_verdict: dict[str, Any] | None
    final_report: dict[str, Any] | None
    risk_score: float

    # --- retry control ---
    attempt: int

    # --- error trail ---
    errors: Annotated[list[str], operator.add]


__all__ = ["AgentState"]

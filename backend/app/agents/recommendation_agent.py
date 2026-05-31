"""Recommendation Agent node.

Synthesises findings from all three specialist agents into ONE explainable
mitigation plan with prioritised actions, owner roles, and timeframes.
Also receives cross-cutting signals (correlations, region hotspots, stockout
predictions) for a holistic risk picture.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.base import _structured_invoke
from app.agents.output_schemas import RecommendationPlan
from app.agents.prompts import RECOMMENDATION_AGENT_PROMPT
from app.agents.state import AgentState


def recommendation_agent(state: AgentState) -> dict[str, Any]:
    """Synthesise specialist findings into a prioritised mitigation plan."""
    findings = {
        d: (state.get(f"{d}_finding") or {})
        for d in ("supplier", "shipment", "inventory")
    }

    def _f(d: str, key: str, fallback: str = "(no finding)") -> str:
        return findings[d].get(key) or fallback

    prompt = RECOMMENDATION_AGENT_PROMPT.format(
        query=state.get("query_rewritten") or state["query"],
        supplier_severity=_f("supplier", "severity", "unknown"),
        supplier_finding=_f("supplier", "finding"),
        supplier_escalation=_f("supplier", "escalation_reason", "none"),
        shipment_severity=_f("shipment", "severity", "unknown"),
        shipment_finding=_f("shipment", "finding"),
        shipment_escalation=_f("shipment", "escalation_reason", "none"),
        inventory_severity=_f("inventory", "severity", "unknown"),
        inventory_finding=_f("inventory", "finding"),
        inventory_escalation=_f("inventory", "escalation_reason", "none"),
        cross_signals=json.dumps(state.get("cross_signals") or {}, default=str)[:600],
    )
    result = _structured_invoke(prompt, RecommendationPlan)
    if result is None:
        from app.agents.output_schemas import MitigationAction
        result = RecommendationPlan(
            executive_summary="(Recommendation Agent unavailable — see agent findings.)",
            actions=[MitigationAction(
                title="Review flagged findings manually",
                owner_role="Supply Chain Manager",
                timeframe_days=7,
                driver="fallback",
                priority=1,
            )],
            risk_score=5.0,
            risk_score_justification="default - LLM unavailable",
            reasoning_trail="(no synthesis)",
        )
    return {
        "recommendation_plan": result.model_dump(),
        "risk_score": float(result.risk_score),
        "agents_invoked": ["recommendation"],
    }


__all__ = ["recommendation_agent"]

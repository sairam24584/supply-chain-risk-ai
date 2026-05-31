"""Query preprocessor and Supervisor Agent nodes.

Preprocessor: rewrites the raw query, detects intent, prepares context.
Supervisor:   LLM-backed router that decides which specialist agents to run.
              Uses a heuristic shortcut for high-confidence single-domain queries.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import _structured_invoke
from app.agents.output_schemas import SupervisorPlan
from app.agents.prompts import SUPERVISOR_PROMPT
from app.agents.query_preprocessor import preprocess_query
from app.agents.state import AgentState
from app.core.logging import logger


def query_preprocess_node(state: AgentState) -> dict[str, Any]:
    """Rewrite the user query and classify intent before any retrieval."""
    pre = preprocess_query(state["query"])
    return {
        "query_rewritten": pre.rewritten,
        "intent": pre.intent,
        "intent_confidence": pre.intent_confidence,
        "preprocessing_notes": pre.notes,
        "attempt": state.get("attempt", 0) + 1,
        "agents_invoked": ["preprocessor"],
    }


def supervisor_node(state: AgentState) -> dict[str, Any]:
    """Route query to the appropriate specialist agents.

    Uses a heuristic shortcut when intent confidence >= 0.7 to avoid an
    unnecessary LLM round-trip on clear single-domain queries.
    """
    intent = state.get("intent", "general_overview")
    conf = state.get("intent_confidence", 0.0)

    # Heuristic shortcut for unambiguous intents.
    _fast = {
        "supplier_quality":   dict(run_supplier=True,  run_shipment=False, run_inventory=False),
        "shipment_logistics": dict(run_supplier=False, run_shipment=True,  run_inventory=False),
        "inventory_demand":   dict(run_supplier=False, run_shipment=False, run_inventory=True),
    }
    if conf >= 0.7 and intent in _fast:
        plan = {
            **_fast[intent],
            "needs_retrieval": True,
            "needs_report": True,
            "rationale": f"heuristic shortcut (intent={intent}, conf={conf})",
        }
        logger.info("supervisor_node | fast-path intent={} conf={:.2f}", intent, conf)
        return {"supervisor_plan": plan, "agents_invoked": ["supervisor"]}

    prompt = SUPERVISOR_PROMPT.format(
        intent=intent,
        intent_confidence=conf,
        query=state.get("query_rewritten") or state["query"],
    )
    result = _structured_invoke(prompt, SupervisorPlan)
    plan = (
        result.model_dump()
        if result
        else {
            "needs_retrieval": True,
            "run_supplier": True,
            "run_shipment": True,
            "run_inventory": True,
            "needs_report": True,
            "rationale": "LLM unavailable — default fanout",
        }
    )
    return {"supervisor_plan": plan, "agents_invoked": ["supervisor"]}


__all__ = ["query_preprocess_node", "supervisor_node"]

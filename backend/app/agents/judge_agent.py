"""Quality Judge Agent node.

LLM-as-judge: scores the Recommendation Plan against a rubric:
  - actionable   : every action has owner role + timeframe
  - grounded     : cited entities appear in retrieved context
  - prioritised  : actions are clearly prioritised
  - score_justified : risk score has a defensible justification
  - citations_valid : agent citations match retrieved context

A weak recommendation MUST score low — the judge is intentionally strict.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.base import _structured_invoke
from app.agents.output_schemas import JudgeVerdict
from app.agents.prompts import JUDGE_AGENT_PROMPT
from app.agents.state import AgentState


def judge_agent(state: AgentState) -> dict[str, Any]:
    """Evaluate the recommendation plan for quality and groundedness."""
    plan = state.get("recommendation_plan") or {}
    if not plan or not plan.get("actions"):
        return {"agents_invoked": ["judge"]}

    # Collect all entities mentioned in retrieved hits for ground-truth check.
    entities: set[str] = set()
    all_citations: list[str] = []
    for h in state.get("retrieved_hits", []):
        m = h.get("metadata", {})
        for k in ("supplier", "sku", "route", "carrier", "location", "source_file"):
            v = m.get(k)
            if v:
                entities.add(str(v))
    for d in ("supplier", "shipment", "inventory"):
        f = state.get(f"{d}_finding") or {}
        all_citations.extend(f.get("citations") or [])

    prompt = JUDGE_AGENT_PROMPT.format(
        query=state.get("query_rewritten") or state["query"],
        recommendation_json=json.dumps(plan, indent=2)[:2000],
        retrieved_entities=", ".join(sorted(entities))[:600],
        all_citations=", ".join(all_citations)[:600] or "(none)",
    )
    result = _structured_invoke(prompt, JudgeVerdict)
    if result is None:
        return {"agents_invoked": ["judge"]}
    return {"judge_verdict": result.model_dump(), "agents_invoked": ["judge"]}


__all__ = ["judge_agent"]

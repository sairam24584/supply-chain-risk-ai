"""Report Generation Agent node.

Formats a final, polished Markdown report for the operations manager,
grounded in the Recommendation Plan and per-agent findings.
Skipped (no-op) when the supervisor sets needs_report=False.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.base import _structured_invoke
from app.agents.output_schemas import FinalReport
from app.agents.prompts import REPORT_AGENT_PROMPT
from app.agents.state import AgentState


def report_agent(state: AgentState) -> dict[str, Any]:
    """Generate a polished final report from the recommendation plan."""
    plan = state.get("supervisor_plan") or {}
    if not plan.get("needs_report", True):
        return {"agents_invoked": ["report:skipped"]}
    rec_plan = state.get("recommendation_plan") or {}
    if not rec_plan:
        return {"agents_invoked": ["report:skipped"]}

    findings = {
        "supplier":  state.get("supplier_finding"),
        "shipment":  state.get("shipment_finding"),
        "inventory": state.get("inventory_finding"),
    }
    prompt = REPORT_AGENT_PROMPT.format(
        query=state.get("query_rewritten") or state["query"],
        plan_json=json.dumps(rec_plan, indent=2)[:2000],
        findings_json=json.dumps(findings, indent=2, default=str)[:2000],
    )
    result = _structured_invoke(prompt, FinalReport)
    if result is None:
        return {"agents_invoked": ["report"]}
    return {"final_report": result.model_dump(), "agents_invoked": ["report"]}


__all__ = ["report_agent"]

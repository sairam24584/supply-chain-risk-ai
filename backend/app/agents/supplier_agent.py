"""Supplier Risk Agent node.

Analyses retrieved incident records for supplier-side risks:
  - defect rates, failed inspections, supplier concentration.
Escalates to the Recommendation Agent when defect rate is severe.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import _run_specialist
from app.agents.prompts import SUPPLIER_AGENT_PROMPT
from app.agents.state import AgentState


def supplier_agent(state: AgentState) -> dict[str, Any]:
    """Supplier Risk Agent — runs when supervisor enables it."""
    plan = state.get("supervisor_plan") or {}
    return _run_specialist(
        state,
        prompt_template=SUPPLIER_AGENT_PROMPT,
        analytics_key="supplier_analytics",
        domain="supplier",
        enabled=plan.get("run_supplier", True),
    )


__all__ = ["supplier_agent"]

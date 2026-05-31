"""Inventory Intelligence Agent node.

Analyses retrieved incident records for inventory and demand risks:
  - stockout risk (stock <= 20 units), overstock (>= 80 units),
    days-to-stockout urgency, demand forecast mismatches.
Escalates imminent stockouts to the Recommendation Agent.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import _run_specialist
from app.agents.prompts import INVENTORY_AGENT_PROMPT
from app.agents.state import AgentState


def inventory_agent(state: AgentState) -> dict[str, Any]:
    """Inventory Intelligence Agent — runs when supervisor enables it."""
    plan = state.get("supervisor_plan") or {}
    return _run_specialist(
        state,
        prompt_template=INVENTORY_AGENT_PROMPT,
        analytics_key="inventory_analytics",
        domain="inventory",
        enabled=plan.get("run_inventory", True),
    )


__all__ = ["inventory_agent"]

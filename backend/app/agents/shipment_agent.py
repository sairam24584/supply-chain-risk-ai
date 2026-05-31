"""Shipment Analysis Agent node.

Analyses retrieved incident records for shipping and logistics risks:
  - carrier delay rates, route hotspots, transport mode bottlenecks.
Escalates chronic delay routes to the Recommendation Agent.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import _run_specialist
from app.agents.prompts import SHIPMENT_AGENT_PROMPT
from app.agents.state import AgentState


def shipment_agent(state: AgentState) -> dict[str, Any]:
    """Shipment Analysis Agent — runs when supervisor enables it."""
    plan = state.get("supervisor_plan") or {}
    return _run_specialist(
        state,
        prompt_template=SHIPMENT_AGENT_PROMPT,
        analytics_key="shipment_analytics",
        domain="shipment",
        enabled=plan.get("run_shipment", True),
    )


__all__ = ["shipment_agent"]

"""Shared helpers used by all agent node modules."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage

from app.agents.llm import get_llm
from app.agents.output_schemas import AgentFinding
from app.agents.state import AgentState
from app.core.logging import logger


def _format_hits(hits: list[dict[str, Any]], limit: int = 4) -> str:
    """Format retrieved hits into a concise context string for agent prompts."""
    if not hits:
        return "(no relevant incidents found)"
    lines = []
    for h in hits[:limit]:
        m = h.get("metadata", {})
        anomaly = m.get("anomaly_score")
        anomaly_str = f" anomaly={anomaly:.2f}" if anomaly is not None else ""
        defect = m.get("defect_rate")
        defect_str = f" defect={defect:.2f}%" if isinstance(defect, (int, float)) else ""
        source = m.get("source_file") or m.get("source_label") or m.get("sku") or "?"
        lines.append(
            f"- {h['id']} [src={source}] supplier={m.get('supplier')} loc={m.get('location')} "
            f"sev={m.get('risk_severity')}{defect_str} delay={m.get('delay_status')}{anomaly_str}\n  "
            f"{h.get('text', '')[:200]}"
        )
    return "\n".join(lines)


def _structured_invoke(prompt: str, schema):
    """Call LLM with structured output and return parsed result, or None on error."""
    try:
        llm = get_llm().with_structured_output(schema)
        return llm.invoke([HumanMessage(content=prompt)])
    except Exception as exc:
        logger.exception("Structured LLM call failed: {}", exc)
        return None


def _empty_finding(domain: str, reason: str) -> AgentFinding:
    """Return a placeholder AgentFinding when an agent is unavailable."""
    return AgentFinding(
        finding=f"({domain} agent unavailable: {reason})",
        severity="low",
        escalate=False,
        escalation_reason="",
        entities_referenced=[],
        citations=[],
    )


def _run_specialist(
    state: AgentState,
    prompt_template: str,
    analytics_key: str,
    domain: str,
    enabled: bool,
) -> dict[str, Any]:
    """Generic specialist runner. No-ops cheaply when disabled by supervisor."""
    if not enabled:
        return {f"{domain}_finding": None, "agents_invoked": [f"{domain}:skipped"]}

    snapshot = state.get(analytics_key) or {}
    prompt = prompt_template.format(
        query=state.get("query_rewritten") or state["query"],
        context=_format_hits(state.get("compressed_hits") or state.get("retrieved_hits", [])),
        analytics=json.dumps(snapshot, default=str, indent=2)[:1200],
    )
    result = _structured_invoke(prompt, AgentFinding)
    if result is None:
        result = _empty_finding(domain, "LLM error or invalid structured output")

    update: dict[str, Any] = {
        f"{domain}_finding": result.model_dump(),
        "agents_invoked": [domain],
    }
    if result.escalate:
        update["escalations"] = [{
            "agent": domain,
            "severity": result.severity,
            "reason": result.escalation_reason or "unspecified",
        }]
    return update


__all__ = ["_format_hits", "_structured_invoke", "_empty_finding", "_run_specialist"]

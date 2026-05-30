"""All LangGraph nodes — preprocessor, supervisor, retrieve, specialists,
recommendation, judge, report.

Structured outputs (Pydantic + tool calling) everywhere. Compressed context.
Per-agent citation tracking. Supervisor-routed.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage

from app.agents.llm import get_llm
from app.agents.output_schemas import (
    AgentFinding,
    FinalReport,
    JudgeVerdict,
    RecommendationPlan,
    SupervisorPlan,
)
from app.agents.prompts import (
    INVENTORY_AGENT_PROMPT,
    JUDGE_AGENT_PROMPT,
    RECOMMENDATION_AGENT_PROMPT,
    REPORT_AGENT_PROMPT,
    SHIPMENT_AGENT_PROMPT,
    SUPERVISOR_PROMPT,
    SUPPLIER_AGENT_PROMPT,
)
from app.agents.query_preprocessor import compress_context, preprocess_query
from app.agents.state import AgentState
from app.core.logging import logger
from app.services import analytics, intelligence
from app.services.retriever import get_retriever


# ---------- helpers ----------

def _format_hits(hits: list[dict[str, Any]], limit: int = 4) -> str:
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
            f"{h.get('text','')[:200]}"
        )
    return "\n".join(lines)


def _structured_invoke(prompt: str, schema):
    try:
        llm = get_llm().with_structured_output(schema)
        return llm.invoke([HumanMessage(content=prompt)])
    except Exception as exc:
        logger.exception("Structured LLM call failed: {}", exc)
        return None


def _empty_finding(domain: str, reason: str) -> AgentFinding:
    return AgentFinding(
        finding=f"({domain} agent unavailable: {reason})",
        severity="low",
        escalate=False,
        escalation_reason="",
        entities_referenced=[],
        citations=[],
    )


# ---------- nodes ----------

def query_preprocess_node(state: AgentState) -> dict[str, Any]:
    """Rewrite + intent detection in front of everything else."""
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
    """LLM-backed router that picks which specialists to run.

    Uses heuristic shortcut when intent confidence is high to skip an LLM call.
    """
    intent = state.get("intent", "general_overview")
    conf = state.get("intent_confidence", 0.0)

    # Heuristic shortcut — saves a full LLM round-trip in clear cases.
    fast_plan = {
        "supplier_quality":          dict(run_supplier=True,  run_shipment=False, run_inventory=False),
        "shipment_logistics":        dict(run_supplier=False, run_shipment=True,  run_inventory=False),
        "inventory_demand":          dict(run_supplier=False, run_shipment=False, run_inventory=True),
    }
    if conf >= 0.7 and intent in fast_plan:
        plan = {
            **fast_plan[intent],
            "needs_retrieval": True,
            "needs_report": True,
            "rationale": f"heuristic shortcut (intent={intent}, conf={conf})",
        }
        return {"supervisor_plan": plan, "agents_invoked": ["supervisor"]}

    prompt = SUPERVISOR_PROMPT.format(
        intent=intent,
        intent_confidence=conf,
        query=state.get("query_rewritten") or state["query"],
    )
    result = _structured_invoke(prompt, SupervisorPlan)
    plan = (result.model_dump() if result else
            {"needs_retrieval": True, "run_supplier": True, "run_shipment": True,
             "run_inventory": True, "needs_report": True,
             "rationale": "LLM unavailable → default fanout"})
    return {"supervisor_plan": plan, "agents_invoked": ["supervisor"]}


def retrieve_node(state: AgentState) -> dict[str, Any]:
    retriever = get_retriever()
    hits = retriever.retrieve(
        query=state.get("query_rewritten") or state["query"],
        top_k=state.get("top_k") or 8,
        where=state.get("filters"),
        rerank=True,
    )
    compressed = compress_context(hits, max_chars_per_chunk=220, max_chunks=5)
    logger.info("retrieve_node | hits={} compressed={}", len(hits), len(compressed))

    supplier_snapshot = analytics.supplier_risk_ranking(top_n=5)
    shipment_snapshot = analytics.shipment_risk_summary()
    inventory_snapshot = analytics.inventory_risk_list(top_n=8)
    correlations = intelligence.get_correlations()
    region_snapshot = intelligence.region_risk_summary()
    stockout_snapshot = intelligence.stockout_predictions(top_n=5)

    cross = {
        "top_numeric_correlations": correlations["numeric"][:3],
        "top_categorical_associations": correlations["categorical"][:3],
        "hotspot_region": region_snapshot.get("hotspot"),
        "top_disrupted_regions": region_snapshot.get("top_disrupted", [])[:3],
        "imminent_stockouts": stockout_snapshot[:5],
    }
    return {
        "retrieved_hits": hits,
        "compressed_hits": compressed,
        "supplier_analytics": {"top_5": supplier_snapshot},
        "shipment_analytics": {
            "hotspots": shipment_snapshot["hotspots"][:5],
            "by_mode": shipment_snapshot["by_transport_mode"],
            "total_delay_rate": shipment_snapshot["delay_rate"],
        },
        "inventory_analytics": {"at_risk": inventory_snapshot, "stockout_predictions": stockout_snapshot},
        "cross_signals": cross,
        "agents_invoked": ["retriever"],
    }


def _run_specialist(state: AgentState, prompt_template: str, analytics_key: str,
                    domain: str, enabled: bool) -> dict[str, Any]:
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


def supplier_agent(state: AgentState) -> dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    return _run_specialist(state, SUPPLIER_AGENT_PROMPT, "supplier_analytics",
                           "supplier", plan.get("run_supplier", True))


def shipment_agent(state: AgentState) -> dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    return _run_specialist(state, SHIPMENT_AGENT_PROMPT, "shipment_analytics",
                           "shipment", plan.get("run_shipment", True))


def inventory_agent(state: AgentState) -> dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    return _run_specialist(state, INVENTORY_AGENT_PROMPT, "inventory_analytics",
                           "inventory", plan.get("run_inventory", True))


def recommendation_agent(state: AgentState) -> dict[str, Any]:
    findings = {d: (state.get(f"{d}_finding") or {}) for d in ("supplier", "shipment", "inventory")}

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
        result = RecommendationPlan(
            executive_summary="(Recommendation Agent unavailable — see agent findings.)",
            actions=[], risk_score=5.0,
            risk_score_justification="default - LLM unavailable",
            reasoning_trail="(no synthesis)",
        )
    return {
        "recommendation_plan": result.model_dump(),
        "risk_score": float(result.risk_score),
        "agents_invoked": ["recommendation"],
    }


def judge_agent(state: AgentState) -> dict[str, Any]:
    plan = state.get("recommendation_plan") or {}
    if not plan or not plan.get("actions"):
        return {"agents_invoked": ["judge"]}

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


def report_agent(state: AgentState) -> dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    if not plan.get("needs_report", True):
        return {"agents_invoked": ["report:skipped"]}
    rec_plan = state.get("recommendation_plan") or {}
    if not rec_plan:
        return {"agents_invoked": ["report:skipped"]}

    findings = {
        "supplier": state.get("supplier_finding"),
        "shipment": state.get("shipment_finding"),
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


__all__ = [
    "query_preprocess_node",
    "supervisor_node",
    "retrieve_node",
    "supplier_agent",
    "shipment_agent",
    "inventory_agent",
    "recommendation_agent",
    "judge_agent",
    "report_agent",
]

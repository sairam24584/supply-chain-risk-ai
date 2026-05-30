"""Natural-language query endpoint — full Phase 2 pipeline.

Cache layers (in order):
  1. Exact-match TTL cache
  2. Semantic embedding-similarity cache

Then:
  Input guardrails  →  LangGraph (preprocess → supervisor → retrieve → 3 specialists
  → recommendation → judge → report)  →  retry-on-low-quality  →
  Output guardrails (incl. citation verification).
"""
from typing import Any

from fastapi import APIRouter, HTTPException

from app.agents.graph import get_graph
from app.core.logging import logger
from app.models.schemas import AgentFindings, QueryRequest, QueryResponse
from app.services.analytics import get_df
from app.services.guardrails import check_input, check_output
from app.services.query_cache import get_query_cache
from app.services.retry_loop import run_with_retry
from app.services.semantic_cache import get_semantic_cache

router = APIRouter(prefix="/api", tags=["query"])


def _allowed_entities() -> tuple[set[str], set[str], set[str]]:
    df = get_df()
    suppliers = set(df["Supplier name"].unique())
    skus = set(df["SKU"].unique())
    # Allow uploaded source filenames too so citations to "policy.pdf" are valid
    sources: set[str] = set()
    return suppliers, skus, sources


def _render_finding_text(f: dict[str, Any] | None, domain: str) -> str:
    if not f:
        return f"({domain} agent did not run)"
    parts = [f.get("finding", "")]
    if f.get("severity"):
        parts.append(f"[severity: {f['severity']}]")
    if f.get("escalate"):
        parts.append(f"[escalated: {f.get('escalation_reason','')}]")
    if f.get("entities_referenced"):
        parts.append(f"[entities: {', '.join(f['entities_referenced'])}]")
    return "  ".join(p for p in parts if p)


def _render_plan_text(plan: dict[str, Any] | None) -> str:
    if not plan:
        return ""
    lines = [plan.get("executive_summary", ""), "", "Top actions:"]
    for i, a in enumerate(plan.get("actions") or [], start=1):
        lines.append(
            f"{i}. {a.get('title')} — Owner: {a.get('owner_role')}, "
            f"Timeframe: {a.get('timeframe_days')}d, Priority: {a.get('priority')} "
            f"(driver: {a.get('driver')})"
        )
    lines.append("")
    lines.append(
        f"Risk score: {plan.get('risk_score')}/10 — {plan.get('risk_score_justification','')}"
    )
    lines.append("")
    lines.append(f"Reasoning: {plan.get('reasoning_trail','')}")
    return "\n".join(lines)


def _collect_citations(final: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for d in ("supplier", "shipment", "inventory"):
        f = final.get(f"{d}_finding") or {}
        out.extend(f.get("citations") or [])
    return out


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest) -> QueryResponse:
    # --- input guardrail ---
    guard_in = check_input(payload.query)
    if not guard_in.ok:
        raise HTTPException(
            status_code=400,
            detail={"message": "query rejected", "violations": guard_in.violations},
        )

    exact_cache = get_query_cache()
    sem_cache = get_semantic_cache()

    # --- 1. exact-match cache fast-path ---
    if payload.use_cache:
        cached, ts = exact_cache.get(guard_in.value, payload.top_k, payload.filters)
        if cached is not None:
            logger.info("cache HIT (exact) | q='{}'", guard_in.value[:60])
            return QueryResponse(
                **cached,
                cache_hit=True,
                cache_type="exact",
                cached_at=ts,
                thread_id=payload.thread_id,
            )

        # --- 2. semantic-similarity cache ---
        sem_val, sem_ts, sem_match = sem_cache.get(guard_in.value)
        if sem_val is not None:
            logger.info(
                "cache HIT (semantic) | q='{}' match='{}' sim={}",
                guard_in.value[:50], (sem_match or {}).get("matched_query","")[:50],
                (sem_match or {}).get("similarity"),
            )
            return QueryResponse(
                **sem_val,
                cache_hit=True,
                cache_type="semantic",
                cache_match=sem_match,
                cached_at=sem_ts,
                thread_id=payload.thread_id,
            )

    # --- invoke graph (with retry loop) ---
    graph = get_graph()
    invoke_config = {"configurable": {"thread_id": payload.thread_id}} if payload.thread_id else None

    def _runner(state, config):
        try:
            return graph.invoke(state, config=config)
        except Exception as exc:
            logger.exception("Agent graph failed: {}", exc)
            raise HTTPException(500, f"agent pipeline error: {exc}")

    initial_state = {
        "query": guard_in.value,
        "filters": payload.filters,
        "top_k": payload.top_k,
    }
    final, attempts, judge_scores = run_with_retry(
        runner=_runner,
        initial_state=initial_state,
        config=invoke_config,
        threshold=0.5,
        max_retries=1,
    )

    plan = final.get("recommendation_plan")
    answer_text = _render_plan_text(plan)

    # --- output guardrail (incl. citation verification) ---
    suppliers, skus, sources = _allowed_entities()
    citations = _collect_citations(final)
    guard_out = check_output(
        answer_text,
        allowed_suppliers=suppliers,
        allowed_skus=skus,
        allowed_sources=sources,
        citations=citations,
    )

    source_list = [
        {
            "id": h.get("id"),
            "metadata": h.get("metadata", {}),
            "rrf_score": h.get("rrf_score"),
            "rerank_score": h.get("rerank_score"),
        }
        for h in final.get("retrieved_hits", [])
    ]

    supplier_text = _render_finding_text(final.get("supplier_finding"), "supplier")
    shipment_text = _render_finding_text(final.get("shipment_finding"), "shipment")
    inventory_text = _render_finding_text(final.get("inventory_finding"), "inventory")

    response_payload = {
        "answer": guard_out.value,
        "sources": source_list,
        "risk_score": final.get("risk_score"),
        "agents_invoked": list(dict.fromkeys(final.get("agents_invoked", []))),
        "findings": AgentFindings(
            supplier=supplier_text,
            shipment=shipment_text,
            inventory=inventory_text,
        ).model_dump(),
        "escalations": final.get("escalations") or [],
        "guardrail_violations": guard_in.violations + guard_out.violations,
        "recommendation_plan": plan,
        "judge_verdict": final.get("judge_verdict"),
        "final_report": final.get("final_report"),
        "agent_findings": {
            "supplier": final.get("supplier_finding"),
            "shipment": final.get("shipment_finding"),
            "inventory": final.get("inventory_finding"),
        },
        "query_rewritten": final.get("query_rewritten"),
        "intent": final.get("intent"),
        "intent_confidence": final.get("intent_confidence"),
        "supervisor_plan": final.get("supervisor_plan"),
        "attempts": attempts,
        "judge_scores": judge_scores,
    }

    if payload.use_cache:
        exact_cache.set(guard_in.value, payload.top_k, payload.filters, response_payload)
        sem_cache.set(guard_in.value, response_payload)

    return QueryResponse(
        **response_payload,
        cache_hit=False,
        cache_type=None,
        cached_at=None,
        thread_id=payload.thread_id,
    )


@router.get("/cache/stats")
async def cache_stats() -> dict:
    return {
        "exact": get_query_cache().stats(),
        "semantic": get_semantic_cache().stats(),
    }


@router.post("/cache/clear")
async def cache_clear() -> dict:
    e = get_query_cache().clear()
    s = get_semantic_cache().clear()
    return {"cleared_exact": e, "cleared_semantic": s}

"""Natural-language query endpoint — full Phase 2 pipeline.

Cache layers (in order):
  1. Exact-match TTL cache
  2. Semantic embedding-similarity cache

Then:
  Input guardrails  →  LangGraph (preprocess → supervisor → retrieve → 3 specialists
  → recommendation → judge → report)  →  retry-on-low-quality  →
  Output guardrails (incl. citation verification).
"""
import re
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

# ── Greeting / chitchat / identity short-circuit ─────────────────────────────
_GREETINGS = re.compile(
    r"^\s*(hi+|hello+|hey+|howdy|yo+|hiya|sup|greetings"
    r"|good\s*(morning|afternoon|evening|day)"
    r"|what'?s\s*up|how\s*are\s*you"
    r"|who\s+(are|r)\s+you"
    r"|what\s+(are|r)\s+you"
    r"|what\s+is\s+your\s+\w+"        # what is your name/purpose/role/goal
    r"|what'?s\s+your\s+\w+"          # what's your name etc.
    r"|tell\s+me\s+about\s+your(self)?"
    r"|are\s+you\s+an?\s+(ai|bot|assistant|model)"
    r"|what\s+can\s+you\s+do"
    r"|how\s+(do\s+you\s+work|can\s+you\s+help)"
    r"|help)\s*[!?.,]?\s*$",
    re.IGNORECASE,
)
_GREETING_REPLY = (
    "Hello! I'm the Supply Chain Risk Intelligence Assistant — "
    "an AI-powered system that analyses your operational data to identify risks "
    "across suppliers, shipments, and inventory.\n\n"
    "You can ask me things like:\n"
    "• \"Which suppliers have the highest defect rates?\"\n"
    "• \"Are there shipment routes with chronic delays?\"\n"
    "• \"Which SKUs are at stockout risk this week?\"\n"
    "• \"Recommend a mitigation plan for our highest severity incidents.\""
)

# ── Out-of-scope friendly response ────────────────────────────────────────────
_OUT_OF_SCOPE_REPLY = (
    "I'm focused on supply chain risk analysis — I can help with questions about "
    "suppliers, shipments, inventory levels, delivery delays, defect rates, and "
    "operational disruptions. Try asking something like: "
    "\"Which suppliers are creating the most quality risk?\""
)

# ── Data-lookup short-circuit (no LLM needed) ─────────────────────────────────
# Maps regex → (df_column, label) for simple enumeration queries.
_DATA_LOOKUPS = [
    (re.compile(r"\b(location|locations|city|cities|region|regions)\b", re.I),
     "Location", "locations in our supply chain network"),
    (re.compile(r"\b(product type|product types|product categor|categories|category)\b", re.I),
     "Product type", "product categories"),
    # Explicit listing only — NOT "which suppliers have highest defect rates"
    (re.compile(r"\b(list|show|give)\b.*\b(supplier|suppliers)\b"
                r"|\b(supplier|suppliers)\b.*\b(list|all|available|network)\b"
                r"|\bwhat\s+suppliers\b|\ball\s+suppliers\b", re.I),
     "Supplier name", "suppliers"),
    (re.compile(r"\b(carrier|carriers|transport vendor|transport vendors|shipping vendor|shipping vendors)\b", re.I),
     "Shipping carriers", "shipping carriers / transport vendors"),
    (re.compile(r"\b(transport mode|transport modes|transportation mode|modes of transport)\b", re.I),
     "Transportation modes", "transportation modes"),
    (re.compile(r"\b(list|show|give)\b.*\b(route|routes)\b"
                r"|\b(route|routes)\b.*\b(list|all|available)\b", re.I),
     "Routes", "shipping routes"),
    # "what products are there", "list all SKUs", "what products do we have"
    (re.compile(r"\b(list|show|give)\b.*\b(sku|skus|product|products)\b"
                r"|\b(sku|skus|product|products)\b.*\b(list|all|available|there|have|our)\b"
                r"|\bwhat\s+(sku|skus|product|products)\b", re.I),
     "SKU", "SKUs / products"),
]

# Analytical intent — if present, skip short-circuit and use full LLM pipeline.
_ANALYTICAL_RE = re.compile(
    r"\b(highest|lowest|worst|best|most|least|top|bottom|rank|rate|rates|"
    r"average|avg|mean|trend|compare|comparison|risk|anomal|perform|defect|"
    r"delay|delayed|score|recommend|mitigation|analysis|analyze|analyse|"
    r"forecast|predict|why|cause|impact|affect|increase|decrease|improve|"
    r"creating|causing|at\s+risk|critical|severe|urgent)\b",
    re.IGNORECASE,
)

# Dataset meta-questions → describe the loaded dataset without hitting the LLM.
_DATASET_META_RE = re.compile(
    r"\b(what\s+data|which\s+data|what\s+dataset|what\s+information|"
    r"what\s+kind\s+of\s+data|what\s+type\s+of\s+data|"
    r"data\s+are\s+we|data\s+do\s+we|applying|using\s+for|"
    r"what\s+is\s+(the\s+)?(dataset|data\s+set|source\s+data))\b",
    re.IGNORECASE,
)


def _try_data_lookup(query: str) -> str | None:
    """Answer simple enumeration/meta questions directly from the DataFrame.
    Analytical questions (risk, defect, delay, etc.) always go to the LLM pipeline."""
    q = query.lower()

    # Dataset meta-question: "what data are we applying risk intelligence to?"
    if _DATASET_META_RE.search(q):
        df = get_df()
        suppliers = sorted(df["Supplier name"].dropna().unique().tolist())
        locations = sorted(df["Location"].dropna().unique().tolist())
        product_types = sorted(df["Product type"].dropna().unique().tolist())
        skus = df["SKU"].dropna().nunique()
        rows = len(df)
        return (
            f"The assistant is analysing a supply chain operations dataset with "
            f"{rows} records across {skus} SKUs.\n\n"
            f"Suppliers ({len(suppliers)}): {', '.join(suppliers)}\n"
            f"Locations ({len(locations)}): {', '.join(locations)}\n"
            f"Product types ({len(product_types)}): {', '.join(product_types)}\n\n"
            f"Risk intelligence covers supplier quality (defect rates, inspections), "
            f"shipment & logistics (carrier delays, route performance), and "
            f"inventory (stockout risk, overstock, lead times)."
        )

    # Skip enumeration short-circuit if query has analytical intent
    if _ANALYTICAL_RE.search(q):
        return None

    # Must look like a listing/enumeration question
    if not re.search(r"\b(what|which|list|show|give|tell|all|how many|any|there)\b", q):
        return None

    df = get_df()
    for pattern, column, label in _DATA_LOOKUPS:
        if pattern.search(query):
            if column not in df.columns:
                continue
            values = sorted(df[column].dropna().unique().tolist())
            if not values:
                return f"No {label} found in the current dataset."
            formatted = ", ".join(str(v) for v in values)
            return (
                f"The following {label} are present in our supply chain dataset "
                f"({len(values)} total):\n\n{formatted}"
            )
    return None


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
    # --- greeting / chitchat short-circuit (skip full pipeline) ---
    if _GREETINGS.match(payload.query.strip()):
        return QueryResponse(
            answer=_GREETING_REPLY,
            agents_invoked=["greeting-handler"],
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- input guardrail ---
    guard_in = check_input(payload.query)
    if not guard_in.ok:
        # Return a friendly response instead of an HTTP error so the UI shows
        # a readable message rather than raw JSON.
        friendly = _OUT_OF_SCOPE_REPLY if "out_of_scope" in guard_in.violations else (
            "Your message couldn't be processed. "
            "Please rephrase and try again."
        )
        return QueryResponse(
            answer=friendly,
            agents_invoked=["guardrail"],
            guardrail_violations=guard_in.violations,
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- data lookup short-circuit (no LLM needed) ---
    data_answer = _try_data_lookup(guard_in.value)
    if data_answer:
        return QueryResponse(
            answer=data_answer,
            agents_invoked=["data-lookup"],
            cache_hit=False,
            thread_id=payload.thread_id,
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
    # Use 1 retry with GPT-4o-mini (quality gain worth it); 0 with Groq (avoids 2× latency)
    from app.core.config import get_settings as _gs
    _max_retries = 1 if _gs().openai_api_key else 0
    final, attempts, judge_scores = run_with_retry(
        runner=_runner,
        initial_state=initial_state,
        config=invoke_config,
        threshold=0.5,
        max_retries=_max_retries,
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

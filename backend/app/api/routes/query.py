"""Natural-language query endpoint — full Phase 2 pipeline."""
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

# ── Greeting / capabilities ───────────────────────────────────────────────────
_GREETINGS = re.compile(
    r"^\s*(hi+|hello+|hey+|howdy|yo+|hiya|sup|greetings|hello\s+there|hey\s+there|hi\s+there"
    r"|good\s*(morning|afternoon|evening|day)"
    r"|what'?s\s*up|how\s*are\s*you"
    r"|who\s+(are|r)\s+you"
    r"|what\s+(are|r)\s+you"
    r"|what\s+is\s+your\s+\w+"
    r"|what'?s\s+your\s+\w+"
    r"|tell\s+me\s+about\s+your(self)?"
    r"|are\s+you\s+an?\s+(ai|bot|assistant|model)"
    r"|what\s+can\s+you\s+do"
    r"|how\s+(do\s+you\s+work|can\s+you\s+help)"
    r"|can\s+you\s+answer\s+(anything|questions?|me)"
    r"|what\s+(topics?|questions?|things?)\s+can\s+you"
    r"|help)\s*[!?.,]?\s*$",
    re.IGNORECASE,
)
_GREETING_REPLY = (
    "Hello! I'm the Supply Chain Risk Intelligence Assistant.\n\n"
    "I analyse your operational supply chain data to surface risks across "
    "suppliers, shipments, and inventory. Ask me things like:\n"
    "- \"Which suppliers have the highest defect rates?\"\n"
    "- \"Are there shipment routes with chronic delays?\"\n"
    "- \"Which SKUs are at stockout risk this week?\"\n"
    "- \"Recommend a mitigation plan for our highest severity incidents.\"\n\n"
    "My answers are grounded in your actual operational data — not general knowledge."
)

# ── SCM concept short-circuit ─────────────────────────────────────────────────
_SCM_CONCEPT_RE = re.compile(
    r"^\s*what\s+is\s+(supply\s+chain|scm|supply-chain|"
    r"risk\s+(analysis|intelligence|management)|"
    r"demand\s+(planning|forecast)|logistics\s+risk|"
    r"procurement\s+risk|inventory\s+risk|shipment\s+risk)\b",
    re.IGNORECASE,
)
_SCM_CONCEPT_REPLY = (
    "Supply chain risk analysis is the process of identifying, assessing, and "
    "mitigating risks across the end-to-end supply chain.\n\n"
    "This assistant focuses on three risk domains from your operational data:\n"
    "- Supplier quality risk: defect rates, failed inspections, concentration risk\n"
    "- Shipment & logistics risk: carrier delays, route hotspots, lead time breaches\n"
    "- Inventory risk: stockout exposure, overstock, days-to-stockout\n\n"
    "Try: \"Which suppliers have the highest defect rates?\" or "
    "\"Which SKUs are at stockout risk this week?\""
)

# ── Personnel / role-definition redirect ──────────────────────────────────────
# "Who is a procurement lead?", "what does an inventory manager do?" etc.
# These are about people/org roles — not in our operational dataset.
_PERSONNEL_RE = re.compile(
    r"^\s*(who\s+is\s+(a\s+|an\s+|the\s+)?|what\s+does\s+(a\s+|an\s+)?|"
    r"what\s+(is|are)\s+(a\s+|an\s+)?(\w+\s+)?role\s+of\s+)"
    r"(procurement\s*(lead|manager|officer)?|"
    r"inventory\s*(manager|lead|controller|planner)?|"
    r"supply\s+chain\s*(manager|lead|analyst|coordinator|director)?|"
    r"logistics\s*(manager|coordinator|lead)?|"
    r"warehouse\s*(manager|supervisor|lead)?|"
    r"quality\s+(assurance|control)\s*(lead|manager|analyst)?|"
    r"qa\s*(lead|manager)?|"
    r"demand\s*(planner|planning\s+manager)?|"
    r"operations\s*(manager|lead)?)\b",
    re.IGNORECASE,
)
_PERSONNEL_REPLY = (
    "This assistant is grounded in your operational supply chain data — "
    "I work with metrics like defect rates, shipment delays, stock levels, and incident records, "
    "but I don't have personnel records or org chart information.\n\n"
    "If you're looking for risk insights, try:\n"
    "- \"Which suppliers are creating the most quality risk?\"\n"
    "- \"Which SKUs are at stockout risk?\"\n"
    "- \"What are the top shipment delays this week?\""
)

# ── "Earlier you said / you mentioned" — conversation reference handler ────────
# The LLM pipeline runs fresh each turn with no memory of previous answers.
# These queries ask about a prior response — redirect gracefully to re-run analysis.
_MEMORY_REF_RE = re.compile(
    r"^\s*(earlier\s+you\s+(said|told|mentioned|stated|answered)"
    r"|you\s+(said|told\s+me|mentioned|stated|answered)"
    r"|but\s+you\s+(said|told|mentioned)"
    r"|you\s+previously\s+(said|mentioned|stated)"
    r"|according\s+to\s+you"
    r"|in\s+your\s+(previous|last|earlier)\s+(response|answer|reply)"
    r"|you\s+just\s+said"
    r"|didn.t\s+you\s+say"
    r"|wasn.t\s+it\s+you\s+who\s+said)",
    re.IGNORECASE,
)

def _memory_ref_reply(query: str) -> str:
    import re as _re
    # Extract any supplier/entity mentioned so we can re-run for them
    entity_match = _re.search(
        r"\b(Supplier\s+\d+|SKU\d+|Carrier\s+[A-Z]|Route\s+[A-Z])\b",
        query, _re.IGNORECASE
    )
    if entity_match:
        entity = entity_match.group(1)
        return (
            f"I don't retain memory between responses — each answer is generated fresh "
            f"from your operational data.\n\n"
            f"Let me re-run the analysis for {entity} right now based on the latest data. "
            f"Try: \"What is the quality risk for {entity}?\""
        )
    return (
        "I don't retain memory of previous responses — each answer is generated fresh "
        "from your current operational data, so numbers may shift as the retrieved "
        "incidents vary.\n\n"
        "For consistent supplier rankings, ask: \"Which suppliers are creating the most "
        "quality risk?\" — this always returns analytics-backed rankings in the same order."
    )

# ── Out-of-scope reply ────────────────────────────────────────────────────────
_OUT_OF_SCOPE_REPLY = (
    "That's outside what I can help with — I'm focused on operational supply chain risk: "
    "supplier quality, shipment delays, inventory levels, and disruption analysis.\n\n"
    "Try: \"Which suppliers are creating the most quality risk?\""
)

# ── Data-lookup short-circuit ─────────────────────────────────────────────────
_DATA_LOOKUPS = [
    (re.compile(r"\b(location|locations|city|cities|region|regions)\b", re.I),
     "Location", "locations in our supply chain network"),
    (re.compile(r"\b(product type|product types|product categor|categories|category)\b", re.I),
     "Product type", "product categories"),
    (re.compile(r"\b(list|show|give)\b.*\b(supplier|suppliers)\b"
                r"|\b(supplier|suppliers)\b.*\b(list|all|available|network)\b"
                r"|\bwhat\s+suppliers\b|\ball\s+suppliers\b"
                r"|\bwho\s+are\s+(the\s+)?(supplier|suppliers)\b", re.I),
     "Supplier name", "suppliers"),
    (re.compile(r"\b(carrier|carriers|transport vendor|shipping vendor)\b", re.I),
     "Shipping carriers", "shipping carriers / transport vendors"),
    (re.compile(r"\b(transport mode|transport modes|transportation mode|modes of transport)\b", re.I),
     "Transportation modes", "transportation modes"),
    (re.compile(r"\b(list|show|give)\b.*\b(route|routes)\b"
                r"|\b(route|routes)\b.*\b(list|all|available)\b", re.I),
     "Routes", "shipping routes"),
    (re.compile(r"\b(list|show|give)\b.*\b(sku|skus|product|products)\b"
                r"|\b(sku|skus|product|products)\b.*\b(list|all|available|there|have|our)\b"
                r"|\bwhat\s+(sku|skus|product|products)\b", re.I),
     "SKU", "SKUs / products"),
]

_ANALYTICAL_RE = re.compile(
    r"\b(highest|lowest|worst|best|most|least|top|bottom|rank|rate|rates|"
    r"average|avg|mean|trend|compare|comparison|risk|anomal|perform|defect|"
    r"delay|delayed|score|recommend|mitigation|analysis|analyze|analyse|"
    r"forecast|predict|why|cause|impact|affect|increase|decrease|improve|"
    r"creating|causing|at\s+risk|critical|severe|urgent)\b",
    re.IGNORECASE,
)

_DATASET_META_RE = re.compile(
    r"\b(what\s+data|which\s+data|what\s+dataset|what\s+information|"
    r"what\s+kind\s+of\s+data|what\s+type\s+of\s+data|"
    r"data\s+are\s+we|data\s+do\s+we|applying|using\s+for|"
    r"what\s+is\s+(the\s+)?(dataset|data\s+set|source\s+data))\b",
    re.IGNORECASE,
)

# ── Per-thread context for comparison rewrites ────────────────────────────────
_thread_context: dict[str, dict] = {}

_ENTITY_RE = re.compile(
    r"\b(Supplier\s+\d+|SKU\d+|Carrier\s+[A-Z](?:\s+[A-Z])?|Route\s+[A-Z](?:\s+[A-Z])?)\b",
    re.IGNORECASE,
)

_SWITCH_ENTITY_RE = re.compile(
    r"^\s*(?:what|how)\s+about\s+(?:the\s+)?"
    r"|^\s*and\s+(?:for\s+|what\s+about\s+)?"
    r"|^\s*same\s+(?:for|with)\s+"
    r"|^\s*compare\s+(?:with\s+|to\s+)?",
    re.IGNORECASE,
)


def _try_data_lookup(query: str) -> str | None:
    q = query.lower()

    if _DATASET_META_RE.search(q):
        df = get_df()
        suppliers = sorted(df["Supplier name"].dropna().unique().tolist())
        locations = sorted(df["Location"].dropna().unique().tolist())
        product_types = sorted(df["Product type"].dropna().unique().tolist())
        skus = df["SKU"].dropna().nunique()
        rows = len(df)
        return (
            f"I'm analysing a supply chain operations dataset with "
            f"{rows} records across {skus} SKUs.\n\n"
            f"Suppliers ({len(suppliers)}): {', '.join(suppliers)}\n"
            f"Locations ({len(locations)}): {', '.join(locations)}\n"
            f"Product types ({len(product_types)}): {', '.join(product_types)}\n\n"
            f"Coverage: supplier quality (defect rates, inspections), "
            f"shipment logistics (carrier delays, route performance), "
            f"and inventory (stockout risk, overstock, lead times)."
        )

    if _ANALYTICAL_RE.search(q):
        return None

    if not re.search(r"\b(what|which|who|list|show|give|tell|all|how many|any|there)\b", q):
        return None

    df = get_df()
    for pattern, column, label in _DATA_LOOKUPS:
        if pattern.search(query):
            if column not in df.columns:
                continue
            values = sorted(df[column].dropna().unique().tolist())
            if not values:
                return f"No {label} found in the current dataset."

            if column == "SKU" and len(values) > 15:
                if "Product type" in df.columns:
                    by_type = (
                        df.groupby("Product type")["SKU"]
                        .nunique()
                        .sort_values(ascending=False)
                    )
                    lines = [
                        f"The dataset contains {len(values)} SKUs across "
                        f"{len(by_type)} product categories:\n"
                    ]
                    for ptype, count in by_type.items():
                        examples = sorted(
                            df[df["Product type"] == ptype]["SKU"].dropna().unique().tolist()
                        )[:3]
                        lines.append(f"- {ptype}: {count} SKUs (e.g. {', '.join(examples)})")
                    lines.append("\nAsk about specific SKUs or categories to see risk details.")
                    return "\n".join(lines)

            formatted = ", ".join(str(v) for v in values)
            return (
                f"The following {label} are present in our dataset "
                f"({len(values)} total):\n\n{formatted}"
            )
    return None


def _allowed_entities() -> tuple[set[str], set[str], set[str]]:
    df = get_df()
    suppliers = set(df["Supplier name"].unique())
    skus = set(df["SKU"].unique())
    sources: set[str] = set()
    return suppliers, skus, sources


def _render_finding_text(f: dict[str, Any] | None, domain: str) -> str:
    if not f:
        return f"({domain} agent did not run)"
    parts = [f.get("finding", "")]
    if f.get("severity"):
        parts.append(f"[severity: {f['severity']}]")
    if f.get("escalate"):
        parts.append(f"[escalated: {f.get('escalation_reason', '')}]")
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
        f"Risk score: {plan.get('risk_score')}/10 — {plan.get('risk_score_justification', '')}"
    )
    lines.append(f"\nReasoning: {plan.get('reasoning_trail', '')}")
    return "\n".join(lines)


def _collect_citations(final: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for d in ("supplier", "shipment", "inventory"):
        f = final.get(f"{d}_finding") or {}
        out.extend(f.get("citations") or [])
    return out


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest) -> QueryResponse:

    # --- greeting / capabilities ---
    if _GREETINGS.match(payload.query.strip()):
        return QueryResponse(
            answer=_GREETING_REPLY,
            agents_invoked=["greeting-handler"],
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- SCM concept ---
    if _SCM_CONCEPT_RE.match(payload.query.strip()):
        return QueryResponse(
            answer=_SCM_CONCEPT_REPLY,
            agents_invoked=["concept-handler"],
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- personnel / role-definition questions → redirect ---
    if _PERSONNEL_RE.match(payload.query.strip()):
        return QueryResponse(
            answer=_PERSONNEL_REPLY,
            agents_invoked=["redirect-handler"],
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- conversation memory reference → graceful redirect ---
    if _MEMORY_REF_RE.match(payload.query.strip()):
        return QueryResponse(
            answer=_memory_ref_reply(payload.query.strip()),
            agents_invoked=["memory-ref-handler"],
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- input guardrail ---
    guard_in = check_input(payload.query)
    if not guard_in.ok:
        friendly = _OUT_OF_SCOPE_REPLY if "out_of_scope" in guard_in.violations else (
            "Your message couldn't be processed. Please rephrase and try again."
        )
        return QueryResponse(
            answer=friendly,
            agents_invoked=["guardrail"],
            guardrail_violations=guard_in.violations,
            cache_hit=False,
            thread_id=payload.thread_id,
        )

    # --- data lookup (no LLM needed) ---
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

    # --- exact-match cache ---
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

        # --- semantic-similarity cache ---
        sem_val, sem_ts, sem_match = sem_cache.get(guard_in.value)
        if sem_val is not None:
            logger.info("cache HIT (semantic) | q='{}'", guard_in.value[:50])
            return QueryResponse(
                **sem_val,
                cache_hit=True,
                cache_type="semantic",
                cache_match=sem_match,
                cached_at=sem_ts,
                thread_id=payload.thread_id,
            )

    # --- comparison context injection ---
    # "what about Supplier 3?" after asking about Supplier 2 → rewrite with comparison framing
    query_to_use = guard_in.value
    if payload.thread_id:
        prev_ctx = _thread_context.get(payload.thread_id)
        if prev_ctx and _SWITCH_ENTITY_RE.match(guard_in.value):
            new_entities = _ENTITY_RE.findall(guard_in.value)
            prev_entities = prev_ctx.get("entities", [])
            prev_intent = prev_ctx.get("intent", "supplier_quality").replace("_", " ")
            if new_entities:
                new_e = new_entities[0]
                if prev_entities:
                    # Full comparison: "what about Supplier 1?" after "Supplier 2 risk?"
                    prev_e = ", ".join(prev_entities)
                    query_to_use = (
                        f"Analyze {new_e} for {prev_intent} risk and improvement opportunities, "
                        f"comparing its performance to {prev_e}."
                    )
                else:
                    # No prior entity (e.g. after generic "which suppliers have highest risk?")
                    # → rewrite as a focused entity query so LLM knows what to answer
                    query_to_use = (
                        f"What is the {prev_intent} risk profile for {new_e}? "
                        f"Show its analytics ranking, avg defect rate, and key risk factors."
                    )
                logger.info("comparison rewrite | '{}' -> '{}'", guard_in.value[:60], query_to_use[:80])

    # --- full LangGraph pipeline ---
    graph = get_graph()
    invoke_config = {"configurable": {"thread_id": payload.thread_id}} if payload.thread_id else None

    def _runner(state, config):
        try:
            return graph.invoke(state, config=config)
        except Exception as exc:
            logger.exception("Agent graph failed: {}", exc)
            raise HTTPException(500, f"agent pipeline error: {exc}")

    initial_state = {
        "query": query_to_use,
        "filters": payload.filters,
        "top_k": payload.top_k,
    }

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

    # --- output guardrail ---
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

    # Store context for next-turn comparison rewrites
    if payload.thread_id:
        entities = _ENTITY_RE.findall(guard_in.value)
        _thread_context[payload.thread_id] = {
            "query": guard_in.value,
            "intent": final.get("intent") or "",
            "entities": list(entities),
        }

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

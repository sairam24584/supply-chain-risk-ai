# Design Decisions & Trade-offs

This document explains the *why* behind the major design choices in the
AI-Powered Supply Chain Risk Intelligence Assistant. Per the project spec, the
deliverable Design Doc must cover: vector database selection, chunking
strategy, hybrid vs semantic-only retrieval, agent orchestration architecture,
anomaly detection strategy, and operational reliability guardrails.

---

## 1. Vector database — Chroma over FAISS / Pinecone / Weaviate

**Decision:** Chroma (persistent client, local filesystem).

**Why:**
- The dataset (100 rows × derived narratives) is tiny — a managed cloud
  vector DB (Pinecone, Weaviate) is overkill and adds latency, cost, and a
  network failure surface.
- Chroma's killer feature for this project is **first-class metadata
  filtering**. The system requirements explicitly ask for filtering on
  supplier, warehouse, shipment status, severity — Chroma's `where={...}`
  parameter handles this natively. FAISS would force us to build our own
  metadata index alongside the vector index.
- Chroma persists to disk by default (`PersistentClient(path=...)`), so the
  index survives restarts without us writing a save/load layer.
- Single process, single dependency, drop-in.

**When we'd switch:**
- If the corpus grows past ~1M vectors, Chroma's HNSW becomes the bottleneck
  and we'd move to a managed service or a Postgres + pgvector setup.
- If we needed multi-tenant isolation or fine-grained access control.

---

## 2. Chunking strategy — Recursive semantic chunking on synthesised narratives

**Decision:** Convert each CSV row into a compact natural-language "incident
record" first, then apply LangChain's `RecursiveCharacterTextSplitter`
(chunk = 600 chars, overlap = 80).

**Why narratives first?**
The source is a relational CSV. Embedding raw rows (or JSON dumps) gives
embeddings clustered by *schema* rather than *meaning* — an embedding of
`{supplier: 'Supplier 2', defect_rate: 3.81, ...}` looks structurally similar
to every other row. Synthesising a prose narrative
(*"SKU24 (skincare) supplied by Supplier 2 in Mumbai. Stock level 4 units
(stockout_risk); Inspection Pending; defect rate 3.69%…"*) lets the embedding
model encode the *meaning* of the row.

**Why recursive + 600/80?**
- Each narrative averages ~520 characters → most rows fit in a single chunk,
  which preserves the full incident context for retrieval.
- The recursive splitter respects sentence boundaries first
  (`["\n\n", "\n", ". ", " ", ""]`), so when a chunk does have to split, it
  splits cleanly between sentences.
- Overlap of 80 catches the few cases where a key field spans the boundary.

**Trade-off considered:** "structured retrieval" (embedding fields independently
and joining) would be more flexible for analytical queries, but the spec
asks for *semantic* retrieval over operational incidents, and our analytical
queries are already handled deterministically by `/api/suppliers/risk` etc.

---

## 3. Hybrid retrieval — BM25 + semantic + RRF + cross-encoder rerank

**Decision:** Four-stage hybrid pipeline:

```
query → ┬─► Chroma semantic search (top 20)
        └─► BM25 keyword search   (top 20)
                    │
                    ▼
        Reciprocal Rank Fusion (k = 60)
                    │
                    ▼
        Cross-encoder reranker (top_k)
```

**Why not semantic-only?**
Semantic embeddings are great at conceptual matches (*"quality issues"* →
documents about defects, inspections, returns) but they consistently
*underrate exact-token matches* on entity names like `Supplier 2` or
`Carrier B`. Operational queries are very entity-heavy — operators ask
"what's happening with Carrier B?" and expect Carrier B rows first. BM25
nails this; embeddings often don't.

**Why RRF (k = 60)?**
RRF is the canonical fusion approach: it's parameter-light (one tunable `k`),
score-agnostic (you don't need to normalise BM25 vs cosine scores), and
robust to having one retriever fail to find anything. `k = 60` is the value
from the original RRF paper and matches the Microsoft/Azure AI Search
default.

**Why a cross-encoder on top?**
RRF mixes ranks, not relevance. A cross-encoder (`ms-marco-MiniLM-L-6-v2`)
scores each *(query, document)* pair jointly through a small transformer —
this catches relevance that neither BM25 nor a bi-encoder embedding sees
(e.g. negation, query-document role swaps). MS-MARCO MiniLM is the standard
"cheap but strong" reranker: 22M params, runs on CPU in ~50ms for 20 docs.

**Trade-off considered:** running the reranker is the single biggest
latency cost per query (~200-400ms). We expose `rerank: bool = True` on
`/api/retrieve` so we can A/B and switch off in latency-critical paths.

---

## 4. Agent orchestration — LangGraph parallel fanout with A2A reducer

**Decision:** Four specialists run in parallel after a shared retrieval
node; recommendation joins them.

```
START → retrieve → [Supplier · Shipment · Inventory] (parallel) → Recommendation → END
```

**Why parallel-then-join, not a router?**
A router (LLM picks which specialists to run) is the obvious alternative but
it introduces:
- An extra LLM call before any analysis starts
- A choice we get wrong some fraction of the time
- Hard reasoning over which combinations make sense

In this domain, every operational question benefits from *all three lenses*.
A "supplier risk" question almost always has shipping and inventory
implications. Always-fanning-out costs ~3× LLM calls but the per-call cost
is small (`gpt-4o-mini`), latency is hidden by parallelism, and the result
quality is higher because the Recommendation Agent gets a complete picture.

**A2A escalation channel.**
Each specialist returns a structured tag: `ESCALATE: yes|no - <reason>`. The
parser extracts these into a shared `escalations: Annotated[list, operator.add]`
state field. LangGraph's reducer pattern means three parallel writers can
append without race conditions. The Recommendation Agent reads this list
explicitly when synthesising — so when (e.g.) the Supplier Agent escalates
"concentrated Fail inspections" and the Inventory Agent escalates "stockout
risk", both signals flow into the final plan with provenance.

**Trade-off considered:** a true ReAct-style agent with tools (each specialist
could call its own analytics endpoint mid-reasoning) would be more powerful
but harder to debug, more LLM-expensive, and harder to evaluate. The current
fixed topology is the right choice for a 100-row dataset and a 10-minute demo.

---

## 5. LLM choice — GPT-4o-mini primary, Groq Llama-3.1-8b fallback

**Decision:** OpenAI-compatible client wired through `langchain_openai.ChatOpenAI`,
swapping `base_url` to Groq when the OpenAI key is missing or the request fails.

**Why GPT-4o-mini?**
- Strong instruction-following at low cost (~$0.0001 per agent call)
- Predictable output formatting (important for our `SEVERITY:` / `ESCALATE:`
  parsers)
- Native function-calling if we ever extend to tool-using agents

**Why Groq as fallback?**
- Sub-second latency, even for 8B-parameter models
- Identical OpenAI-compatible API → no second client to maintain
- Free tier suffices for development

The factory is cached (`@lru_cache`) and probes OpenAI first; if either the
key is unset or initialisation fails, it falls back to Groq. The agents are
unaware of the choice.

---

## 6. Anomaly detection — derived risk fields at ingest time

**Decision:** Compute risk severities at ingest, not at query time.

In `app/services/data_loader.py`:

| Field | Rule |
| --- | --- |
| `defect_severity` | `defect_rate ≥ 3 → high`, `≥ 1 → medium`, else `low` |
| `stock_status` | `stock_level ≤ 20 → stockout_risk`, `≥ 80 → overstock`, else `healthy` |
| `delay_status` | `shipping_time ≥ 8 OR lead_time ≥ 25 → delayed`; `shipping_time ≥ 5 → moderate`; else `on_time` |
| `risk_severity` (aggregate) | weighted sum: defect severity + 2·stockout + 2·delayed + 3·Fail + 1·Pending; thresholded at 4 / 7 |

**Why not statistical anomaly detection (Isolation Forest, z-score)?**
- The corpus is small (100 rows) — statistical models will pick up noise
- The domain has well-defined operational thresholds (e.g. "defect rate
  above 3% is a quality incident") that experts already agree on
- Deterministic rules are *explainable* — a key spec requirement
- The thresholds are centralised at the top of `data_loader.py`, so tuning
  is a one-line change

**Surfaced through:**
- Chroma metadata → all retrieval can filter by `risk_severity`, `stock_status`, …
- Analytics endpoints → dashboard tiles, supplier ranking
- Agent prompts → each specialist references the severity bands explicitly

For larger production datasets we'd layer an Isolation Forest / z-score on
top to catch *unknown unknowns*, but the deterministic layer stays as the
explainability backbone.

---

## 7. Operational reliability guardrails

The system runs **two** guardrails around every LLM call.

### Input guardrails (`app/services/guardrails.py::check_input`)

| Check | What it catches | Action |
| --- | --- | --- |
| Length | empty / > 1000 chars | hard reject (400) |
| Prompt injection | "ignore previous", "system prompt", "jailbreak", "act as a different AI" | hard reject |
| In-scope | no supply-chain vocabulary token in query | hard reject |
| PII | emails, phones, card-like, API keys | redact, allow through |

The in-scope check uses a curated 30-word domain vocabulary
(`supplier`, `warehouse`, `inventory`, `shipment`, …). This is cheap and
deterministic; a future enhancement would be an LLM-based classifier with the
heuristic as a fast-path.

### Output guardrails (`app/services/guardrails.py::check_output`)

| Check | What it catches | Action |
| --- | --- | --- |
| Hallucinated supplier | `Supplier N` not in dataset (e.g. `Supplier 99`) | flag in `guardrail_violations`, keep answer |
| Hallucinated SKU | `SKU####` not in dataset | flag |
| PII leakage | emails / phones / keys in the LLM output | redact |
| Empty output | LLM returned nothing | hard reject |

Hallucinated entities are *flagged but not blocked* — we surface them on the
response so the UI can show a "verify these claims" badge instead of hiding
the answer. The product trade-off: blocking on hallucination would lose
useful answers when the LLM gets entity names slightly wrong; flagging keeps
the user informed.

### Why no commercial guardrail library (Guardrails-AI, NeMo)?

- The rule set is small and domain-specific; a regex pass is faster, simpler,
  and trivially auditable
- No additional dependency, no LLM-based guardrail latency
- The interface (`GuardResult.value`, `GuardResult.violations`) keeps the
  door open to swap in a heavier framework later without changing route code

---

## 8. Evaluation — DeepEval (not RAGAS)

**Decision:** Standardise on DeepEval.

**Why:**
- Spec explicitly names it in Requirement 2
- DeepEval's **G-Eval** supports *custom rubrics* for LLM-as-judge — we use
  it to score "mitigation quality" (actionable? grounded? prioritised?
  justified risk score?)
- DeepEval also covers the standard RAG metrics RAGAS provides
  (`FaithfulnessMetric`, `AnswerRelevancyMetric`), so we don't lose anything
- Pytest-style harness means we can wire eval to CI later without
  a second framework

The golden set lives in `backend/scripts/eval_golden.py`; the runner is
`backend/scripts/eval.py`.

---

## 9. Observability — LangSmith via env vars

LangSmith integrates with LangChain/LangGraph through environment variables
(`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`).
`app/core/tracing.py::setup_tracing()` translates our `LANGSMITH_*` config
into the variables LangChain reads — a tiny shim that keeps our config
names consistent with the spec's terminology.

Once enabled, every agent invocation produces a trace with:
- The retrieval call (with sources)
- All four LLM calls (3 specialists + 1 recommendation)
- Per-call latency, token counts, and inputs/outputs
- Errors surfaced cleanly

This is invaluable for prompt tuning — we can see exactly when an agent
fails to follow the `FINDING: / SEVERITY: / ESCALATE:` format and adjust.

---

## 10. Frontend — React + Vite + Tailwind (not raw HTML, not Streamlit)

**Decision:** React for an enterprise-grade UI; Vite proxy to FastAPI.

**Why:**
- The user requested "enterprise level UI"; Streamlit/Gradio look like demos
- Tailwind + Recharts + Lucide give us a clean, professional look without
  designer time
- Vite's `/api` proxy means CORS is invisible in development
- React Router enables a multi-page app (`/dashboard`, `/query`, …) without
  bundler complexity
- Single SPA can be served as static assets from Render's free static-site
  tier in deployment

---

## Design Decision 10 — Multi-tier query routing before the LangGraph graph

**Problem:** The full agent pipeline (embedding → retrieval → 3 LLM calls → judge) takes 5–15 seconds. Many legitimate queries — greetings, dataset meta-questions, simple enumeration, domain concept explanations — do not need any LLM invocation.

**Decision:** A layered short-circuit chain is evaluated in order before the LangGraph graph is invoked:

```
Incoming query
  │
  ├─ Greeting / identity regex          → instant reply, no LLM
  ├─ SCM domain-concept regex           → canned explanation, no LLM
  ├─ General-knowledge blocker          → out-of-scope reply, no LLM
  ├─ Guardrail (PII, injection, scope)  → reject or redact
  ├─ Data-lookup short-circuit          → answer from DataFrame, no LLM
  ├─ Exact-match TTL cache              → cached response
  ├─ Semantic similarity cache          → cached response
  └─ LangGraph multi-agent pipeline     → full LLM reasoning
```

**Trade-offs:**
- The data-lookup layer uses an `_ANALYTICAL_RE` guard to prevent intercepting questions that look like enumerations but are actually analytical ("which suppliers have the highest defect rates?" matches "suppliers" but contains "highest" → routed to LLM).
- The general-knowledge blocker uses an entity-ref exception list so that "explain supplier risk" (operational) passes through while "what is supply and demand?" (generic economics) is blocked.
- A 40-query regression test suite guards against regressions in routing logic.

---

## Design Decision 11 — Dynamic retry count per LLM provider

**Problem:** The retry-on-low-quality loop (`run_with_retry`) retries the full agent pipeline if the judge score is below the threshold. With GPT-4o-mini this is worthwhile (quality often improves on retry). With Groq Llama-3.1-8b, structured output compliance is inconsistent — a retry doubles latency with minimal quality gain.

**Decision:** `max_retries` is set dynamically at request time:

```python
max_retries = 1 if settings.openai_api_key else 0
```

This means switching from Groq to GPT-4o-mini (by adding `OPENAI_API_KEY` to `.env`) automatically enables retries with no code change.

---

## Future enhancements (out of scope for v0.1)

1. **Anomaly detection layer** — Isolation Forest over numeric fields,
   surfaced as a fifth specialist agent
2. **Feedback loop** — store query/answer/rating in a small SQLite table,
   feed into DeepEval as ground truth
3. **Real-time data ingestion** — replace one-shot CSV with a streaming
   ingest (Kafka/SQS → upsert into Chroma)
4. **ERP connectors** — read directly from SAP / Oracle SCM tables
5. **Cross-region disruption analysis** — geocoded warehouse data + a
   geospatial filter on retrieval
6. **Per-supplier dashboards** — `/suppliers/:id` page with the same
   multi-agent pipeline scoped to that supplier

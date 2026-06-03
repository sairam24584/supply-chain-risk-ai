# AI-Powered Supply Chain Risk Intelligence Assistant

A production-grade multi-agent RAG system that analyses supply chain risk across suppliers, shipments, and inventory — retrieving historical incidents, detecting anomalies, and generating prioritised mitigation plans via natural-language queries.

> Built end-to-end with FastAPI · LangGraph · Chroma · Hybrid Retrieval · React + Tailwind · DeepEval · LangSmith

---

## Table of Contents

1. [What it does](#what-it-does)
2. [System Architecture](#system-architecture)
3. [End-to-End Flow](#end-to-end-flow)
4. [Multi-Agent Pipeline](#multi-agent-pipeline)
5. [Retrieval System](#retrieval-system)
6. [Analytics & Intelligence](#analytics--intelligence)
7. [Guardrails](#guardrails)
8. [Caching & Memory](#caching--memory)
9. [Proactive Alerting & Feedback Loop](#proactive-alerting--feedback-loop)
10. [Evaluation](#evaluation)
11. [Frontend](#frontend)
12. [Tech Stack](#tech-stack)
13. [Project Layout](#project-layout)
14. [Quick Start](#quick-start)
15. [API Reference](#api-reference)
16. [Demo Flow](#demo-flow)
17. [Known Limitations](#known-limitations)

---

## What It Does

Operations managers interact with a natural-language chat interface to interrogate supply chain data. The system:

- **Identifies risk** — pinpoints which suppliers, shipments, or SKUs are most at risk using live analytics and retrieved incident context
- **Explains findings** — each answer cites the exact defect rates, delay percentages, and stock levels it reasoned from, with source documents attached
- **Recommends actions** — generates a prioritised mitigation plan with owner roles and timeframes, grounded only in data that exists
- **Detects anomalies** — IsolationForest flags statistical outliers across the dataset
- **Alerts proactively** — APScheduler polls every 15 minutes and fires alerts when thresholds are breached
- **Learns from feedback** — thumbs up/down votes reweight retrieval scores for future queries

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         React + Vite UI                             │
│  Dashboard · Query Console · Suppliers · Shipments · Inventory      │
│  Anomalies · Regions · Incident Detail · Alerts                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP / REST
┌──────────────────────────▼──────────────────────────────────────────┐
│                      FastAPI Backend                                 │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                     Query Router                             │    │
│  │  greeting → concept → personnel → memory-ref → guardrail   │    │
│  │  → exact cache → semantic cache → comparison rewrite        │    │
│  │  → LangGraph pipeline                                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │  Analytics   │  │  Intelligence │  │  Proactive Alerting      │  │
│  │  Service     │  │  Service      │  │  (APScheduler 15-min)    │  │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                   LangGraph Multi-Agent System                       │
│                                                                      │
│  preprocess → supervisor → retrieve → [supplier ║ shipment ║       │
│  inventory] → recommendation → judge → report                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐
   │  Chroma DB  │  │  BM25 Index │  │  LLM       │
   │  (vector)   │  │  (keyword)  │  │  (OpenAI / │
   └─────────────┘  └─────────────┘  │   Groq)    │
          │                │          └─────────────┘
          └────────────────┘
               RRF fusion
                   │
          Cross-encoder reranker
          (ms-marco-MiniLM-L-6-v2)
```

Full Mermaid diagrams (system layers, agent flow, ingestion pipeline) are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## End-to-End Flow

### 1. Data Ingestion (one-time)

```
supply_chain_data.csv (100 rows × 22 columns)
        │
        ▼
data_loader.py          — pandas DataFrame, feature engineering
        │                 (stock_status, delay_status, risk_severity, days_to_stockout)
        ▼
chunking.py             — RecursiveCharacterTextSplitter, chunk_size=800, overlap=100
        │                 Each chunk tagged with metadata: supplier, sku, location,
        │                 risk_severity, defect_rate, delay_status, source_file
        ▼
embeddings.py           — text-embedding-3-small (fallback: all-MiniLM-L6-v2)
        │
        ├──▶ vector_store.py   → Chroma persistent DB (100 records)
        └──▶ bm25_index.py     → BM25Okapi in-memory index
```

Run once: `python -m scripts.ingest --rebuild`

### 2. Query Handling

Every POST `/api/query` goes through a multi-tier routing chain **before** the LangGraph pipeline:

```
Raw query
    │
    ├─ Greeting pattern ("hi", "hello") ──────────────────▶ instant reply (no LLM)
    ├─ SCM concept ("what is ROP?") ──────────────────────▶ instant concept reply
    ├─ Personnel question ("who is the supply chain manager?") ▶ redirect reply
    ├─ Memory reference ("earlier you said X") ───────────▶ polite redirect (no hallucination)
    ├─ Input guardrail (PII / injection / out-of-scope) ──▶ 400 error with violations
    ├─ Exact cache hit (SHA-256 of normalised query) ─────▶ cached response
    ├─ Semantic cache hit (cosine ≥ 0.92) ────────────────▶ cached response
    ├─ Comparison rewrite ("what about Supplier 2?") ─────▶ rewrite + continue
    └─ LangGraph multi-agent pipeline ───────────────────▶ full analysis
```

### 3. Agent Pipeline (LangGraph)

See the [Multi-Agent Pipeline](#multi-agent-pipeline) section below.

### 4. Response Assembly

The FastAPI route assembles the final `QueryResponse`:

- `answer` — rendered recommendation plan (executive summary + actions + risk score)
- `recommendation_plan` — structured JSON (executive_summary, actions, risk_score, justification)
- `agent_findings` — per-specialist structured findings (finding, severity, escalate, entities, citations)
- `findings` — human-readable text renderings of each specialist finding
- `judge_verdict` — quality rubric (actionable, grounded, prioritised, score_justified)
- `final_report` — polished markdown report from Report Agent
- `sources` — retrieved incident documents with RRF + rerank scores
- `escalations` — A2A escalation messages between agents
- `guardrail_violations` — any flagged violations (empty if clean)
- `intent`, `intent_confidence`, `query_rewritten` — preprocessing metadata
- `risk_score` — 0–10 overall risk score
- `agents_invoked` — ordered list of agents that ran
- `cache_hit`, `cache_type`, `attempts`, `judge_scores` — pipeline metadata

---

## Multi-Agent Pipeline

The LangGraph graph is a directed acyclic topology with parallel fanout:

```
START
  │
  ▼
query_preprocess_node
  │  • Rewrites ambiguous queries for retrieval
  │  • Classifies intent: supplier_quality | shipment_logistics |
  │    inventory_demand | mitigation_planning | general_overview
  │  • Intent confidence capped at 0.85
  ▼
supervisor_node
  │  • Fast-path heuristic if confidence ≥ 0.7 (skips LLM call)
  │  • Otherwise LLM routes which specialists to run
  │  • Decides: run_supplier, run_shipment, run_inventory, needs_report
  ▼
retrieve_node
  │  • Hybrid retrieval: Chroma + BM25 → RRF fusion → cross-encoder rerank
  │  • Compresses context: deduplicated 220-char heads, max 5 chunks
  │  • Attaches deterministic analytics snapshots (pre-formatted ranked text):
  │      supplier_analytics: Rank 1-5 by overall_risk_score
  │      shipment_analytics: top 5 carrier×route hotspots by delay_rate
  │      inventory_analytics: top 8 SKUs by days_to_stockout (from intelligence service)
  │  • Attaches cross-cutting signals: correlations, region hotspot, stockout predictions
  │
  ├────────────────────┬──────────────────────────┐
  ▼                    ▼                          ▼
supplier_agent    shipment_agent           inventory_agent
  │  (parallel)        │  (parallel)             │  (parallel)
  │  • Reads supplier_analytics (AUTHORITATIVE)  │
  │  • Uses context for qualitative details only │
  │  • Produces AgentFinding: finding, severity, │
  │    escalate, entities_referenced, citations  │
  │                    │                          │
  └────────────────────┴──────────────────────────┘
                       │ fan-in (LangGraph reducer)
                       ▼
          recommendation_agent
            │  • Synthesises all three findings
            │  • Produces RecommendationPlan:
            │      executive_summary (2-3 sentences, specific data)
            │      actions (1-5 MitigationAction with owner + timeframe)
            │      risk_score (0-10), risk_score_justification
            │      reasoning_trail
            ▼
          judge_agent
            │  • LLM-as-judge quality rubric:
            │      actionable, grounded, prioritised,
            │      score_justified, citations_valid
            │  • overall_quality: 0.0–1.0
            │  • If quality < 0.5 AND attempts < max_retries → retry
            ▼
          report_agent
            │  • Skipped if supervisor set needs_report=False
            │  • Generates polished markdown FinalReport:
            │      title, headline, body (4-8 paragraphs), next_steps
            ▼
          END
```

### Data Grounding Strategy

A critical design decision: LLM agents are **not allowed to use retrieved context for numbers**. All quantitative data (defect rates, delay rates, stock levels) come from the pre-computed analytics snapshots passed as formatted text. Retrieved incident documents are used only for qualitative context (incident descriptions, SKU names, locations).

This prevents RAG non-determinism: different document sets retrieved on different runs would otherwise produce different numbers for the same supplier.

### A2A Escalation

If a specialist agent sets `escalate=True`, it writes to the `escalations` list in state (using LangGraph's Annotated list reducer). The Recommendation Agent reads all escalations as part of its `cross_signals` context.

### Retry Loop

`retry_loop.py` wraps the graph invocation. If `judge_verdict.overall_quality < 0.5` and attempts < max_retries, it re-invokes the full pipeline with a fresh state. `max_retries=1` with GPT-4o-mini, `max_retries=0` with Groq (auto-detected).

---

## Retrieval System

### Hybrid Retrieval

```
Query
  │
  ├──▶ Chroma semantic search  (top_k=8)  → hits with cosine scores
  ├──▶ BM25Okapi keyword search (top_k=8)  → hits with BM25 scores
  │
  └──▶ Reciprocal Rank Fusion (RRF, k=60)
            │  Merges both hit lists, rewards documents that rank
            │  highly in both lists
            ▼
       Cross-encoder reranker
            │  model: cross-encoder/ms-marco-MiniLM-L-6-v2
            │  Scores each (query, document) pair directly
            │  Sorts by rerank_score descending
            ▼
       Feedback reweighting
            │  Applies multipliers from SQLite feedback store:
            │  thumbs-up → ×1.25, thumbs-down → ×0.80 per doc_id
            ▼
       Final ranked hits (returned to retrieve_node)
```

### Context Compression

`compress_context()` in `query_preprocessor.py`:
- Takes the top `max_chunks=5` hits
- Truncates each to `max_chars_per_chunk=220` characters (first sentence head)
- Deduplicates using Jaccard similarity on first-sentence tokens (threshold 0.5)

---

## Analytics & Intelligence

### Analytics Service (`analytics.py`)

Pure-pandas computations over the cached DataFrame (pre-warmed at startup):

| Function | Returns |
|---|---|
| `supplier_risk_ranking(top_n)` | Ranked by `risk_index = avg_defect_rate + fail_inspections×1.5 + high_severity×1.2` |
| `shipment_risk_summary()` | Network delay rate, carrier×route hotspots, transport mode stats |
| `inventory_risk_list(top_n)` | At-risk SKUs (stockout_risk, overstock) sorted by urgency |
| `dashboard_summary()` | Total SKUs, severity breakdown, stock/delay status counts |
| `anomaly_summary()` | IsolationForest results |
| `region_risk_summary()` | Per-location risk aggregation |

### Intelligence Service (`intelligence.py`)

Derived analytics requiring more computation:

| Function | Returns |
|---|---|
| `stockout_predictions(top_n)` | Daily velocity → days_to_stockout → urgency label |
| `get_correlations()` | Pearson + Cramér's V between key fields |
| `region_risk_summary()` | Region-level hotspot detection |
| `demand_forecast(sku)` | Simple moving average + trend projection |

### Anomaly Detection (`anomaly.py`)

IsolationForest trained on: `[defect_rate, lead_time, stock_level, shipping_days, revenue]`. Contamination=0.1. Results cached, exposed via `/api/anomalies`.

---

## Guardrails

### Input Guardrail (`check_input`)

Blocks queries containing:
- **PII patterns** — email addresses, phone numbers
- **Prompt injection** — "ignore previous instructions", "jailbreak", etc.
- **Out-of-scope** — queries clearly unrelated to supply chain operations

Returns `GuardResult(ok=False, violations=[...])` → FastAPI returns HTTP 400.

### Output Guardrail (`check_output`)

Scans generated answer for:
- **Hallucinated entities** — supplier names, SKU IDs not present in the allowed set (built from actual dataset)
- **PII leakage** — redacts any PII that slipped through

The allowed entity sets (`allowed_suppliers`, `allowed_skus`, `allowed_sources`) are pre-computed from the CSV at startup.

---

## Caching & Memory

### Exact Cache

SHA-256 hash of `(normalised_query, top_k, filters)`. TTL-based expiry (configurable). Bypassed when `use_cache=False`.

### Semantic Cache (`semantic_cache.py`)

Embeds the query and compares against cached query embeddings. If cosine similarity ≥ 0.92, serves the cached response. Prevents redundant LLM calls for paraphrased queries.

### LangGraph MemorySaver

LangGraph's built-in `MemorySaver` checkpointer persists graph state per `thread_id`. This means the agent graph can resume mid-pipeline if interrupted. Note: this is graph state persistence, not conversation history — LLM prompts do not receive previous turns.

### Thread Context (Comparison Rewrites)

`_thread_context` dict (in-memory, keyed by `thread_id`) stores the most recent query's intent and named entities. Used to rewrite follow-up queries like "what about Supplier 2?" into fully-specified queries for the pipeline.

---

## Proactive Alerting & Feedback Loop

### Proactive Alerting (`alerting.py`)

APScheduler job runs every 15 minutes and evaluates:
- Suppliers with `avg_defect_rate > 3.0%`
- Carrier×route combos with `delay_rate > 0.7` (70%)
- SKUs with `days_to_stockout < 7`

Alerts are persisted to SQLite and exposed via `/api/alerts` and `/api/alerts/summary`.

### Feedback Loop (`feedback.py`)

Users vote thumbs-up or thumbs-down on any response. Votes are stored in SQLite with `(query, vote, doc_id)`. The retriever reads the feedback store and applies score multipliers:

```python
thumbs_up   → score × 1.25  (surface this document more)
thumbs_down → score × 0.80  (surface this document less)
```

Stats exposed at `/api/feedback/stats`.

---

## Evaluation

### DeepEval Harness (`scripts/eval.py`)

Three metrics evaluated against 5 golden test cases:

| Metric | Threshold | What it measures |
|---|---|---|
| `FaithfulnessMetric` | ≥ 0.7 | Answer is grounded in retrieved context (no hallucination) |
| `AnswerRelevancyMetric` | ≥ 0.7 | Answer actually addresses the question |
| `GEval (Mitigation Quality)` | ≥ 0.7 | Custom rubric: actionable + grounded + prioritised + justified score |

```powershell
cd backend
python -m scripts.eval           # full suite (5 cases)
python -m scripts.eval --quick   # first 2 cases only
```

Results saved to `data/eval_results.json`. View at `GET /api/eval/results`.

### LLM-as-Judge (in-pipeline)

`judge_agent` runs on every live query. Scores `overall_quality` 0–1 against rubric:
`actionable`, `grounded`, `prioritised`, `score_justified`, `citations_valid`.

Expected scores: ~70–80% with GPT-4o-mini, ~20% with Groq Llama-3.1-8b-instant (poor structured output compliance).

---

## Frontend

React + Vite + Tailwind CSS. 9 pages:

| Route | Page | Description |
|---|---|---|
| `/` | Dashboard | KPI tiles (severity mix, delay rate, stockout count, avg defect), summary charts |
| `/query` | Query Console | Natural-language chat with full agent response rendering |
| `/suppliers` | Supplier Risk | Risk-index ranking table with drill-down |
| `/shipments` | Shipment Risk | Carrier × route delay heatmap, transport mode breakdown |
| `/inventory` | Inventory Risk | SKU stockout urgency table, overstock flags |
| `/anomalies` | Anomalies | IsolationForest outlier table with anomaly scores |
| `/regions` | Regions | Location-level risk map and aggregation |
| `/data` | Data Explorer | Raw dataset table with filters |
| `/incident/:sku` | Incident Detail | Full SKU row drill-down |

### Query Console Response Card

For a full pipeline response, the UI renders:

1. **Intent badge** — detected intent + confidence (e.g. "supplier quality · 85%")
2. **Cache badge** — "exact cache" or "semantic cache" if served from cache
3. **Executive summary** — 2-3 sentence synthesised answer with specific numbers
4. **Risk score** — colour-coded 0–10 (green < 4, amber 4–7, red ≥ 7)
5. **Top 3 actions** — priority chip + title + owner role + timeframe
6. **Expandable "Full Analysis"** — agent findings, escalations, judge verdict, full action list, report, retrieved sources with RRF/rerank scores, pipeline trace

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Backend framework | **FastAPI** | Native async, auto OpenAPI docs, Pydantic validation |
| Multi-agent orchestration | **LangGraph** | Stateful graph, parallel fanout, built-in reducers, MemorySaver |
| Vector database | **Chroma** (persistent) | Built-in metadata filtering, no separate server needed |
| Embeddings | **OpenAI text-embedding-3-small** / fallback: `all-MiniLM-L6-v2` | Quality with offline fallback |
| Primary LLM | **GPT-4o-mini** (via gateway) | Cost-effective, strong structured output |
| Fallback LLM | **Groq llama-3.3-70b-versatile** | Sub-second latency, capable structured output |
| Keyword retrieval | **BM25Okapi** (rank-bm25) | Precise term matching, complements semantic |
| Reranker | **cross-encoder/ms-marco-MiniLM-L-6-v2** | CPU-friendly, strong relevance reordering |
| Anomaly detection | **IsolationForest** (scikit-learn) | Unsupervised, no labelled data needed |
| Evaluation | **DeepEval** | Spec-mandated; supports G-Eval LLM-as-judge |
| Observability | **LangSmith** | Native LangGraph trace integration |
| Task scheduler | **APScheduler** | Lightweight in-process scheduler for proactive alerts |
| Frontend | **React + Vite + Tailwind + Recharts** | Fast dev, enterprise styling, rich charts |
| Deployment | **Render** (`render.yaml` at root) | Free tier, supports FastAPI + static |

---

## Project Layout

```
supply-chain-risk-ai/
│
├── backend/
│   ├── app/
│   │   ├── main.py                    FastAPI app factory, lifespan, router registration
│   │   │
│   │   ├── core/
│   │   │   ├── config.py              Pydantic Settings (env vars, LLM models, paths)
│   │   │   ├── logging.py             Loguru structured logger
│   │   │   └── tracing.py             LangSmith callback setup
│   │   │
│   │   ├── api/routes/
│   │   │   ├── query.py               Main chat endpoint + multi-tier routing
│   │   │   ├── retrieve.py            Hybrid retrieval debug endpoint
│   │   │   ├── dashboard.py           Aggregate KPI endpoint
│   │   │   ├── intelligence.py        Anomaly, correlation, forecast, stockout, region endpoints
│   │   │   ├── alerts.py              Proactive alert list + summary
│   │   │   ├── feedback.py            Thumbs up/down vote endpoint + stats
│   │   │   ├── upload.py              PDF / CSV document upload + source management
│   │   │   ├── eval.py                DeepEval results endpoint
│   │   │   └── health.py              Liveness probe
│   │   │
│   │   ├── models/
│   │   │   └── schemas.py             QueryRequest, QueryResponse, AgentFindings, etc.
│   │   │
│   │   ├── agents/
│   │   │   ├── state.py               AgentState TypedDict (all graph fields)
│   │   │   ├── graph.py               LangGraph StateGraph wiring
│   │   │   ├── llm.py                 LLM factory (OpenAI → Groq fallback)
│   │   │   ├── prompts.py             All agent prompt templates
│   │   │   ├── output_schemas.py      Pydantic schemas for structured LLM output
│   │   │   ├── base.py                _structured_invoke, _run_specialist helpers
│   │   │   ├── supervisor_node.py     Query preprocessor + supervisor routing node
│   │   │   ├── retrieve_node.py       Hybrid retrieval + analytics snapshot assembly
│   │   │   ├── supplier_agent.py      Supplier Risk Agent
│   │   │   ├── shipment_agent.py      Shipment Analysis Agent
│   │   │   ├── inventory_agent.py     Inventory Intelligence Agent
│   │   │   ├── recommendation_agent.py  Recommendation + synthesis agent
│   │   │   ├── judge_agent.py         LLM-as-judge quality evaluator
│   │   │   ├── report_agent.py        Polished markdown report generator
│   │   │   └── query_preprocessor.py  Intent detection, query rewriting, context compression
│   │   │
│   │   └── services/
│   │       ├── data_loader.py         CSV loader + feature engineering + DataFrame cache
│   │       ├── chunking.py            RecursiveCharacterTextSplitter wrapper
│   │       ├── embeddings.py          OpenAI / sentence-transformers embedding factory
│   │       ├── vector_store.py        Chroma persistent collection wrapper
│   │       ├── bm25_index.py          BM25Okapi index builder + searcher
│   │       ├── reranker.py            MS-MARCO cross-encoder reranker
│   │       ├── retriever.py           Hybrid retriever (Chroma + BM25 + RRF + rerank + feedback)
│   │       ├── analytics.py           Supplier / shipment / inventory analytics (pandas)
│   │       ├── intelligence.py        Stockout predictions, correlations, region analysis
│   │       ├── anomaly.py             IsolationForest anomaly detection
│   │       ├── guardrails.py          Input + output guardrails (PII, injection, hallucination)
│   │       ├── query_cache.py         Exact cache (SHA-256 + TTL)
│   │       ├── semantic_cache.py      Semantic cache (cosine similarity ≥ 0.92)
│   │       ├── alerting.py            APScheduler proactive alert job
│   │       ├── feedback.py            Thumbs vote store (SQLite) + retrieval reweighting
│   │       ├── retry_loop.py          Judge-gated auto-retry wrapper
│   │       ├── document_loaders.py    PDF / DOCX / TXT / CSV loaders
│   │       ├── document_preprocessor.py  Chunk + embed uploaded documents
│   │       └── document_ingestor.py   Upsert uploaded doc chunks into Chroma
│   │
│   └── scripts/
│       ├── ingest.py                  One-shot CSV → Chroma ingestion pipeline
│       ├── eval_golden.py             5 golden test cases with expected answers
│       └── eval.py                    DeepEval runner (faithfulness + relevancy + G-Eval)
│
├── frontend/
│   └── src/
│       ├── api/client.js              Axios client + all API call wrappers
│       ├── components/
│       │   ├── Layout.jsx             Sidebar nav + header + recent query history
│       │   ├── AgentCard.jsx          Collapsible per-agent finding card
│       │   ├── StatusPanel.jsx        Live backend health indicator
│       │   ├── StatCard.jsx           KPI tile component
│       │   ├── RiskBadge.jsx          Colour-coded severity badge
│       │   └── Spinner.jsx            Loading indicator
│       └── pages/
│           ├── QueryConsole.jsx       Main chat page with full response rendering
│           ├── Dashboard.jsx          KPI overview + charts
│           ├── SupplierRisk.jsx       Supplier risk table
│           ├── ShipmentRisk.jsx       Shipment hotspot table
│           ├── InventoryRisk.jsx      Inventory stockout table
│           ├── Anomalies.jsx          IsolationForest outlier table
│           ├── Regions.jsx            Location risk breakdown
│           ├── Data.jsx               Raw data explorer
│           └── IncidentDetail.jsx     Full SKU drill-down
│
├── data/
│   ├── supply_chain_data.csv          Source dataset (100 rows, 22 columns)
│   └── eval_results.json              DeepEval run output (generated)
│
├── docs/
│   ├── ARCHITECTURE.md                Three Mermaid diagrams (system, agents, ingestion)
│   └── project_instructions/         Original project specification
│
├── DESIGN.md                          Design decisions and trade-off rationale
├── NOTES.md                           Session-by-session progress log
├── README.md                          This file
├── requirements.txt                   Python dependencies
├── render.yaml                        Render deployment config
└── .env.example                       Environment variable template
```

---

## Quick Start

### Prerequisites

- Python **3.11**
- Node **18+**
- One of: OpenAI API key / learning gateway key / Groq API key

### 1. Configure environment

```powershell
copy .env.example .env
notepad .env
```

Minimum required keys:

```env
# Option A — learning gateway (training network only)
OPENAI_API_KEY=your_learner_key
OPENAI_BASE_URL=https://keygateway.arshnivlabs.com/v1

# Option B — direct OpenAI
OPENAI_API_KEY=sk-...

# Option C — Groq only (lower quality structured output, no retry)
GROQ_API_KEY=gsk_...

# Optional
LANGSMITH_API_KEY=ls__...
LANGSMITH_TRACING=true
```

### 2. Backend setup

```powershell
cd D:\fde_training\supply-chain-risk-ai

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd backend
python -m scripts.ingest --rebuild
```

Expected output: `Upserted 100 records into 'supply_chain_incidents'.`

### 3. Run backend

```powershell
# from backend/ with .venv active
uvicorn app.main:app --reload --port 8000
```

Verify:
- Health: http://localhost:8000/health
- Swagger: http://localhost:8000/docs

### 4. Run frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### 5. (Optional) Run evaluation

```powershell
cd backend
python -m scripts.eval --quick
```

Results at http://localhost:8000/api/eval/results

---

## API Reference

### Query

| Endpoint | Method | Description |
|---|---|---|
| `/api/query` | POST | Natural-language query → multi-agent analysis |
| `/api/retrieve` | POST | Raw hybrid retrieval (debug) |

#### POST `/api/query`

Request:
```json
{
  "query": "Which suppliers are creating the most quality risk?",
  "top_k": 8,
  "filters": { "risk_severity": "high" },
  "thread_id": "thr_abc123",
  "use_cache": true
}
```

Response:
```json
{
  "answer": "Supplier 4 carries the highest risk (score 26.3) ...",
  "risk_score": 7.5,
  "recommendation_plan": {
    "executive_summary": "Supplier 4 carries the highest composite risk...",
    "actions": [
      {
        "title": "Audit Supplier 4 SKU12 defect root cause",
        "owner_role": "Procurement Lead",
        "timeframe_days": 14,
        "driver": "supplier finding — 12 failed inspections",
        "priority": 1
      }
    ],
    "risk_score": 7.5,
    "risk_score_justification": "Supplier 4 score 26.3 with 2.34% defect rate...",
    "reasoning_trail": "..."
  },
  "agent_findings": {
    "supplier": { "finding": "...", "severity": "high", "escalate": true, ... },
    "shipment": { "finding": "...", "severity": "medium", "escalate": false, ... },
    "inventory": { "finding": "...", "severity": "medium", "escalate": false, ... }
  },
  "judge_verdict": {
    "actionable": true, "grounded": true, "prioritised": true,
    "score_justified": true, "citations_valid": true,
    "overall_quality": 0.82, "rationale": "..."
  },
  "sources": [
    { "id": "incident-SKU24", "rrf_score": 0.029, "rerank_score": 6.4, "metadata": {...} }
  ],
  "escalations": [
    { "agent": "supplier", "severity": "high", "reason": "12 failed inspections" }
  ],
  "guardrail_violations": [],
  "agents_invoked": ["preprocessor", "supervisor", "retriever", "supplier", "shipment", "inventory", "recommendation", "judge", "report"],
  "intent": "supplier_quality",
  "intent_confidence": 0.85,
  "query_rewritten": "Which suppliers have the highest defect rates and quality risks?",
  "cache_hit": false,
  "attempts": 1
}
```

### Analytics

| Endpoint | Method | Description |
|---|---|---|
| `/api/dashboard/summary` | GET | Aggregate KPIs |
| `/api/suppliers/risk?top_n=10` | GET | Supplier risk ranking |
| `/api/shipments/risk` | GET | Carrier × route hotspots |
| `/api/inventory/risk?top_n=20` | GET | At-risk SKUs |
| `/api/incidents/{sku}` | GET | Full SKU row |
| `/api/anomalies` | GET | IsolationForest outliers |
| `/api/correlations` | GET | Pearson + Cramér's V |
| `/api/forecast/{sku}` | GET | Demand forecast |
| `/api/stockout-prediction?top_n=20` | GET | Days-to-stockout ranking |
| `/api/regions/risk` | GET | Location risk summary |

### Other

| Endpoint | Method | Description |
|---|---|---|
| `/api/alerts` | GET | Proactive alert list |
| `/api/alerts/summary` | GET | Alert counts by type/severity |
| `/api/feedback` | POST | Submit thumbs up/down vote |
| `/api/feedback/stats` | GET | Vote aggregates |
| `/api/upload/document` | POST | Upload PDF/DOCX for RAG |
| `/api/upload/csv` | POST | Upload CSV dataset |
| `/api/upload/sources` | GET | List uploaded sources |
| `/api/upload/sources/{name}` | DELETE | Remove uploaded source |
| `/api/cache/stats` | GET | Exact + semantic cache stats |
| `/api/cache/clear` | POST | Flush both caches |
| `/api/eval/results` | GET | Latest DeepEval run results |
| `/health` | GET | Liveness probe |

---

## Demo Flow

Suggested 10-minute panel walkthrough:

| # | Action | What it demonstrates |
|---|---|---|
| 1 | Type "Hi" in Query Console | Instant greeting — zero LLM calls, sub-millisecond |
| 2 | Type "What data are we analysing?" | Instant dataset summary from DataFrame — no LLM |
| 3 | "Which suppliers are creating the most quality risk?" | Full 8-agent pipeline: intent=supplier_quality, parallel fanout, Supplier 4 rank 1 (score 26.3, 2.34% defect, 12 failed inspections) |
| 4 | Expand "Full Analysis" | Show agent findings, escalations, judge score, retrieved sources with RRF+rerank scores, complete action plan |
| 5 | "Are there shipment routes with chronic delays?" | Shipment agent: Carrier C × Route C (71% delay rate, 8.1d avg) |
| 6 | "Which SKUs are at imminent stockout risk?" | Inventory agent: SKU34 Chennai (stock=1, days_to_stockout=0, critical) |
| 7 | "What is the risk associated with Supplier 2?" | Specific-entity focus: Supplier 2 analytics row surfaced first, compared to Supplier 4 |
| 8 | "Earlier you said Supplier 4 was highest risk" | Memory-ref handler: polite redirect, no hallucination, explains no cross-turn memory |
| 9 | Open Dashboard → Anomalies → Alerts | Analytics pages, IsolationForest outliers, proactive threshold alerts |
| 10 | Upload a PDF, re-ask | Show RAG grounding on user-uploaded document |

---

## Ground Truth (Supplier Rankings)

For result verification:

| Rank | Supplier | Risk Score | Avg Defect Rate | Failed Inspections |
|---|---|---|---|---|
| 1 | Supplier 4 | 26.3 | 2.34% | 12 |
| 2 | Supplier 2 | 25.2 | 2.36% | 8 |
| 3 | Supplier 5 | 21.6 | 2.67% | 7 |
| 4 | Supplier 1 | 12.0 | 1.80% | 6 |
| 5 | Supplier 3 | 10.6 | 2.47% | 3 |

Risk score = `avg_defect_rate + failed_inspections × 1.5 + high_severity_incidents × 1.2`

---

## Known Limitations

| Limitation | Impact | Fix |
|---|---|---|
| Groq Llama fallback | Complex structured output (RecommendationPlan) may fail; use `llama-3.3-70b-versatile` | Set `OPENAI_API_KEY` + gateway URL for best results |
| Specialist agents are synchronous | Parallel fanout runs in thread pool — correct but slower than native async | Convert to `async def` post-demo |
| No SSE streaming | UI waits for full pipeline (~5–15s on Groq) | Build `/api/query/stream` endpoint |
| Per-doc Chroma delete | Deleted upload chunks linger until full re-ingest | Track chunk IDs per upload; call `collection.delete(ids=[...])` on removal |
| No per-IP rate limiting | Open to abuse in public deployment | Add `slowapi` middleware |
| Conversation history not injected | LLM has no memory of prior turns; cross-turn questions use rewrite heuristics only | Add rolling message buffer to agent prompts |
| DeepEval requires OpenAI key | Without key, G-Eval metric falls back to heuristics | Run eval suite from training network with gateway key |

---

## License

Internal / training use — Prodapt FDE Capstone Project.

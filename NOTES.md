# Supply Chain Risk Intelligence Assistant — Session Notes

## Project State (as of 2026-05-31)

Architecture: Multi-agent RAG (LangGraph) · FastAPI backend · React+Vite frontend  
Spec match: ~99%  
Backend venv: `D:\fde_training\supply-chain-risk-ai\.venv` (Python 3.11)

## What's Complete
- Hybrid retrieval: BM25 + Chroma + RRF + MS-MARCO cross-encoder reranker
- Full agent pipeline: preprocess → supervisor → retrieve → specialists (parallel fanout) → recommendation → judge → report
- Input/output guardrails + citation verification + dynamic retry loop (0 retries with Groq, 1 with GPT-4o-mini)
- Multi-tier query routing: greeting → SCM concept → data-lookup → general-knowledge block → guardrail → exact cache → semantic cache → LangGraph
- Exact + semantic TTL cache + LangGraph MemorySaver checkpointing
- Anomaly detection (IsolationForest), correlation analysis, demand forecast
- Analytics REST endpoints (dashboard, suppliers, shipments, inventory, anomalies, regions, incidents)
- Multi-format document loaders + preprocessor + ingestor
- AI-assistant chat UI (React, 8 pages, sticky input, Recent queries, file upload)
- Proactive alerting (APScheduler, every 15 min) + alerts REST API
- Feedback loop (thumbs up/down → SQLite → retrieval reweighting ×1.25/×0.80)
- DeepEval harness at `backend/scripts/eval.py` (heuristic scoring with Groq; DeepEval metrics available when OPENAI_API_KEY set)
- 10-slide panel deck: `supply_chain_risk_ai_deck.pptx` (root folder)
- Architecture diagram (3 Mermaid views in docs/ARCHITECTURE.md) + DESIGN.md + README + render.yaml
- DataFrame pre-warm at startup (eliminates cold-start latency on first query)
- Agent prompt fix: citation instructions reworded so Groq does not append literal "Cite X:" lines to prose answers
- Guardrail overhaul: 40-query test suite; general-knowledge blocker + operational entity ref exceptions; action/recommendation vocab expansion

## What's Still Missing (not critical for demo)
1. Async LLM calls — specialists still sync within LangGraph (runs in thread pool; parallel fanout works)
2. Streaming SSE — `/api/query/stream` not built; UI waits for full response
3. Per-doc Chroma delete — chunks linger after file delete from UI
4. Pytest suite + CI
5. Tool-using agents — specialists cannot call analytics endpoints mid-reasoning
6. OCR for scanned PDFs
7. Per-IP rate limit

## Env / Gateway Notes
- Gateway: `https://keygateway.arshnivlabs.com/v1` — IP-allowlisted (training network only)
- Home WiFi / no key: set `OPENAI_API_KEY=` empty → auto-falls back to Groq (Llama-3.1-8b-instant)
- Groq limitations: lower quality structured output, 20% judge scores typical; GPT-4o-mini will score 70–80%+
- Windows SSL fix: `truststore.inject_into_ssl()` at top of `main.py` and `backend/scripts/eval.py`
- Dynamic retry: `max_retries=1` with GPT-4o-mini, `max_retries=0` with Groq (auto-detected from OPENAI_API_KEY)

## Run Commands
```powershell
# Backend
cd D:\fde_training\supply-chain-risk-ai
.venv\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --reload --port 8000

# Frontend
cd D:\fde_training\supply-chain-risk-ai\frontend
npm run dev

# DeepEval (run from backend dir with venv active)
python -m scripts.eval
# Results saved to backend/data/eval_results.json
# View at http://localhost:8000/api/eval/results
```
Open http://localhost:5173

## Demo Flow (10 min)
1. Open http://localhost:5173 → Query Console
2. Greeting: "Hi" → instant greeting (no LLM)
3. Meta: "what data are we analysing?" → instant dataset summary (no LLM)
4. Supplier risk: "Which suppliers have the highest defect rates?"
5. Shipment: "Are there shipment routes with chronic delays?"
6. Inventory: "Which SKUs are at stockout risk this week?"
7. Drill-down: "What is the risk associated with SKU68?"
8. Mitigation: "Recommend a mitigation plan for our highest severity incidents"
9. Show Dashboard → Anomalies → Alerts pages
10. Upload a document → re-query to show RAG grounding

## Smoke Test Results (2026-05-30)
- Data loader: 100 rows, 28 cols ✅
- Analytics (supplier/shipment/inventory/dashboard): all pass ✅
- Anomaly detection: 15/100 anomalies, score range [0,1] ✅
- Alerting service: 46 alerts generated (supplier=5, shipment=6, inventory=20, anomaly=15) ✅
- Feedback service: boost/penalty applied correctly (×1.25 / ×0.80) ✅
- Routes (alerts=3, feedback=2, eval=1): all import cleanly ✅
- Pydantic schemas: QueryRequest/QueryResponse/FeedbackRequest all validate ✅
- Guardrail routing: 40/40 test cases correct ✅

## Session History
- Sessions 1–5: scaffold → agents → analytics → guardrails → DeepEval harness → React frontend → docs → gateway/SSL fix → UI overhaul → cache/memory → Phase 2 (loaders, preprocessor, query rewriter, intent classifier, supervisor, report agent, citation guardrail, retry loop, render.yaml)
- Session 6: proactive alerting (APScheduler) + feedback loop + eval harness fixes + pptx generation + smoke tests
- Session 7: agent file split + greeting/chitchat expansion + UI redesign (compact cards, status panel, sidebar toggle, pipeline progress indicator)
- Session 8: query routing overhaul (data-lookup short-circuit, SCM concept handler, general-knowledge blocker, entity ref exceptions) + agent prompt citation fix + guardrail vocab expansion + 40-query test suite + startup pre-warm + dynamic retry logic

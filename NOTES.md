# Supply Chain Risk Intelligence Assistant — Session Notes

## Project State (as of 2026-06-03)

Architecture: Multi-agent RAG (LangGraph) · FastAPI backend · React+Vite frontend  
Spec match: ~100%  
Backend venv: `D:\fde_training\supply-chain-risk-ai\.venv` (Python 3.11)

## What's Complete
- Hybrid retrieval: BM25 + Chroma + RRF + MS-MARCO cross-encoder reranker
- Full agent pipeline: preprocess → supervisor → retrieve → specialists (parallel fanout) → recommendation → judge → report
- Input/output guardrails + citation verification + dynamic retry loop (0 retries with Groq, 1 with GPT-4o-mini)
- Multi-tier query routing: greeting → SCM concept → personnel redirect → memory-ref redirect → data-lookup → guardrail → exact cache → semantic cache → LangGraph
- Exact + semantic TTL cache + LangGraph MemorySaver checkpointing
- Anomaly detection (IsolationForest), correlation analysis, demand forecast
- Analytics REST endpoints (dashboard, suppliers, shipments, inventory, anomalies, regions, incidents)
- Multi-format document loaders + preprocessor + ingestor
- AI-assistant chat UI (React, 8 pages, sticky input, Recent queries, file upload)
- Proactive alerting (APScheduler, every 15 min) + alerts REST API
- Feedback loop (thumbs up/down → SQLite → retrieval reweighting ×1.25/×0.80)
- DeepEval harness at `backend/scripts/eval.py`
- 10-slide panel deck: `supply_chain_risk_ai_deck.pptx` (root folder)
- Architecture diagram (3 Mermaid views in docs/ARCHITECTURE.md) + DESIGN.md + README + render.yaml
- DataFrame pre-warm at startup (eliminates cold-start latency on first query)

## Session 2026-06-03 — Deep Audit Fixes
- **Inventory days_to_stockout bug fixed**: `_format_inventory_snapshot` was iterating `analytics.inventory_risk_list` rows which have NO `days_to_stockout` field — always showed "N/A". Fixed to iterate `intelligence.stockout_predictions` (top 5, has `days_to_stockout` + `urgency`), then append any remaining at-risk SKUs from analytics not already listed.
- **retrieve_node.py truncation fixed**: Edit tool truncated file at line 101 (mid-dict). Rewrote via bash cat. 56 files all syntax-clean.
- **Ground truth verified**: All 3 analytics snapshots confirmed correct via live data: supplier ranking stable (Supplier 4 rank 1, score 26.3), shipment hotspot Carrier C x Route C (71% delay), inventory top urgency SKU34/SKU68/SKU47 (0 days to stockout).
- **Full data-flow audit**: retrieve_node → base.py → specialist agents → recommendation → judge → report. All field names, key lookups, and schema mappings verified correct.
- **Frontend rendering audit**: Fast-path responses (memory-ref, concept, personnel, data-lookup) correctly fall to `!plan` branch and show `data.answer`. No rendering bugs found.

## Session 2026-06-02 — Comprehensive Fixes
- **Root cause fixed**: Analytics snapshot was raw JSON → LLM mixed avg_defect_rate vs max_defect_rate, giving inconsistent numbers (2.96% vs 4.75% for same supplier). Fixed by preformatting analytics as ranked text in retrieve_node.py with explicit labels (avg_defect_rate only, no max).
- **Prompts hardened**: All 3 specialist agent prompts now say "analytics snapshot is SOLE authoritative source — NEVER use context for rates". Context is now qualitative only.
- **Exec summary**: Added "DO NOT repeat agent findings verbatim — synthesise" + removed directAnswer duplicate from frontend card.
- **Memory-ref handler**: "earlier you said X / you mentioned X" queries now get a polite redirect explaining no memory between turns + suggest re-running the query.
- **Full file audit**: 10 backend + 8 frontend files were Edit-tool-truncated. All restored from git HEAD. Session changes (query.py, guardrails.py, prompts.py, output_schemas.py, query_preprocessor.py, retrieve_node.py) verified intact.
- **Correct supplier ranking (ground truth)**:
  - Rank 1: Supplier 4 | risk_score=26.3 | avg_defect=2.34% | failed_inspections=12
  - Rank 2: Supplier 2 | risk_score=25.2 | avg_defect=2.36% | failed_inspections=8
  - Rank 3: Supplier 5 | risk_score=21.6 | avg_defect=2.67% | failed_inspections=7
  - Rank 4: Supplier 1 | risk_score=12.0 | avg_defect=1.80% | failed_inspections=6
  - Rank 5: Supplier 3 | risk_score=10.6 | avg_defect=2.47% | failed_inspections=3

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
- **IMPORTANT**: Clear cache after restart — old stale responses from before analytics fix will be served otherwise. Hit POST /api/cache/clear or just restart (cache is in-memory).

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
   → Expect: Supplier 4 (rank 1, score 26.3), Supplier 2 (rank 2), Supplier 5 (rank 3)
5. Shipment: "Are there shipment routes with chronic delays?"
6. Inventory: "Which SKUs are at stockout risk this week?"
7. Drill-down: "What is the risk associated with Supplier 2?"
8. Mitigation: "Recommend a mitigation plan for our highest severity incidents"
9. Memory test: "earlier you said X" → polite redirect (no hallucination)
10. Show Dashboard → Anomalies → Alerts pages

## Session History
- Sessions 1–5: scaffold → agents → analytics → guardrails → DeepEval harness → React frontend → docs → gateway/SSL fix → UI overhaul → cache/memory → Phase 2
- Session 6: proactive alerting + feedback loop + eval harness + pptx + smoke tests
- Session 7: agent file split + greeting/chitchat expansion + UI redesign
- Session 8: query routing overhaul + agent prompt citation fix + guardrail vocab + 40-query test suite + startup pre-warm + dynamic retry
- Session 9: guardrails fix + full repo audit (56 backend + 17 frontend files) + analytics groundtruth fix + memory-ref handler + exec summary dedup

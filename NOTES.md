# Supply Chain Risk Intelligence Assistant — Session Notes

## Project State (as of 2026-05-30)

Architecture: Multi-agent RAG (LangGraph) · FastAPI backend · React+Vite frontend  
PDF spec match: ~95%  
Backend venv: `D:\fde_training\supply-chain-risk-ai\.venv` (Python 3.11)

## What's Complete
- Hybrid retrieval: BM25 + Chroma + RRF + MS-MARCO cross-encoder reranker
- Full agent pipeline: preprocess → supervisor → retrieve → specialists (parallel) → recommendation → judge → report
- Input/output guardrails + citation verification + retry-on-low-quality loop
- Exact + semantic TTL cache + LangGraph MemorySaver checkpointing
- Anomaly detection (IsolationForest), correlation analysis, demand forecast
- Analytics REST endpoints (dashboard, suppliers, shipments, inventory, anomalies, regions, incidents)
- Multi-format document loaders + preprocessor + ingestor
- AI-assistant chat UI (React, 8 pages, sticky input, Recent queries, file upload)
- Architecture diagram (3 Mermaid views) + DESIGN.md + README + render.yaml

## What's Missing (priority order)
1. DeepEval — harness exists at `backend/scripts/eval.py`, never executed; no scores stored
2. 10-slide panel deck (.pptx) — not generated yet
3. Async LLM calls — specialists still sync within LangGraph
4. Streaming SSE — `/api/query/stream` not built
5. Per-doc delete from Chroma (chunks linger after file delete)
6. Feedback loop (thumbs up/down → SQLite → retrieval reweighting)
7. Pytest suite + CI
8. Tool-using agents (specialists can't call analytics endpoints mid-reasoning)
9. Proactive alerting (APScheduler)
10. OCR for scanned PDFs
11. Per-IP rate limit

## Env / Gateway Notes
- Gateway: `https://keygateway.arshnivlabs.com/v1` — IP-allowlisted (training network only)
- Home WiFi: set `OPENAI_API_KEY=` empty → auto-falls back to Groq (Llama-3.1-8b)
- Windows SSL fix: `truststore.inject_into_ssl()` at top of `main.py`

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
```
Open http://localhost:5173

## Session History
- Sessions 1–5: scaffold → agents → analytics → guardrails → DeepEval harness → React frontend → docs → gateway/SSL fix → UI overhaul → cache/memory → Phase 2 (loaders, preprocessor, query rewriter, intent classifier, prompt compression, supervisor, report agent, citation guardrail, retry loop, render.yaml)

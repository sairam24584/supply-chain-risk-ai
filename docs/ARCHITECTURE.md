# Architecture

Three diagrams: **system layers**, **multi-agent flow**, and **ingestion pipeline**.
All Mermaid sources render natively on GitHub and VS Code (Markdown Preview).

---

## 1. System architecture (layered view)

```mermaid
flowchart TB
    %% =============== FRONTEND ===============
    subgraph FE["🖥️ Frontend — React + Vite + Tailwind"]
        direction LR
        FE_Dash[Dashboard]
        FE_Query[Query Console]
        FE_Sup[Supplier Risk]
        FE_Ship[Shipment Risk]
        FE_Inv[Inventory Risk]
        FE_Detail[SKU Detail]
    end

    %% =============== API LAYER ===============
    subgraph API["⚡ FastAPI Backend"]
        direction TB
        subgraph Routes["HTTP Routes"]
            direction LR
            R_Det["GET /api/dashboard/summary<br/>GET /api/suppliers/risk<br/>GET /api/shipments/risk<br/>GET /api/inventory/risk<br/>GET /api/incidents/{sku}"]
            R_LLM["POST /api/query<br/>POST /api/retrieve"]
        end
        subgraph Guard["🛡️ Guardrails"]
            G_In[Input<br/>scope · injection · PII]
            G_Out[Output<br/>hallucination · PII]
        end
    end

    %% =============== BUSINESS LOGIC ===============
    subgraph Logic["Business Logic"]
        direction LR
        subgraph Analytics["📊 Analytics Service<br/>(deterministic · no LLM)"]
            A_Sup[supplier_risk_ranking]
            A_Ship[shipment_risk_summary]
            A_Inv[inventory_risk_list]
            A_Dash[dashboard_summary]
        end
        subgraph Agents["🤖 LangGraph Multi-Agent System"]
            G_Graph[Compiled StateGraph]
        end
    end

    %% =============== RAG STACK ===============
    subgraph RAG["🔍 RAG Stack"]
        direction TB
        H_Retr[Hybrid Retriever]
        BM25[BM25 Index]
        Chroma[(Chroma Vector DB)]
        Rerank[Cross-Encoder Reranker<br/>MS-MARCO MiniLM-L-6]
        BM25 -. keyword .-> H_Retr
        Chroma -. semantic .-> H_Retr
        H_Retr --> RRF[Reciprocal Rank Fusion]
        RRF --> Rerank
    end

    %% =============== EXTERNAL ===============
    subgraph LLM["🧠 LLM Factory"]
        Primary[GPT-4o-mini<br/>OpenAI]
        Fallback[Llama-3.1-8b<br/>Groq]
    end

    subgraph Obs["📡 Observability"]
        LS[LangSmith Tracing]
    end

    subgraph Data["💾 Data Layer"]
        CSV[(supply_chain_data.csv<br/>100 rows · 24 cols)]
        Loader[Data Loader<br/>+ risk derivation<br/>+ narrative gen]
        Emb[Embeddings<br/>OpenAI text-embed-3-small<br/>+ MiniLM fallback]
    end

    %% --- wires ---
    FE_Dash --> R_Det
    FE_Sup --> R_Det
    FE_Ship --> R_Det
    FE_Inv --> R_Det
    FE_Detail --> R_Det
    FE_Query --> R_LLM

    R_Det --> Analytics
    Analytics --> Loader

    R_LLM --> G_In --> Agents
    Agents --> G_Out --> R_LLM

    G_Graph --> H_Retr
    G_Graph --> LLM
    G_Graph -.-> LS

    CSV --> Loader
    Loader --> Emb --> Chroma
    Loader --> BM25
    LLM -.-> LS

    classDef api fill:#e0f2fe,stroke:#0369a1,stroke-width:2px
    classDef rag fill:#fef3c7,stroke:#b45309
    classDef llm fill:#ede9fe,stroke:#6d28d9
    classDef data fill:#f1f5f9,stroke:#475569
    classDef guard fill:#fee2e2,stroke:#dc2626
    class API api
    class RAG rag
    class LLM llm
    class Data data
    class Guard guard
```

---

## 2. Multi-agent flow (LangGraph topology)

```mermaid
flowchart LR
    Start([Query in]) --> Retrieve[retrieve_node<br/>Hybrid RAG]

    Retrieve --> Supplier[Supplier Risk Agent<br/>defect/inspection lens]
    Retrieve --> Shipment[Shipment Analysis Agent<br/>carrier/route/delay lens]
    Retrieve --> Inventory[Inventory Intelligence<br/>stockout/overstock lens]

    Supplier -. A2A escalation .-> Rec
    Shipment -. A2A escalation .-> Rec
    Inventory -. A2A escalation .-> Rec

    Supplier --> Rec[Recommendation Agent<br/>synthesise · prioritise · score]
    Shipment --> Rec
    Inventory --> Rec

    Rec --> End([Answer + risk score])

    classDef parallel fill:#fef3c7,stroke:#b45309
    classDef joiner fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px
    class Supplier,Shipment,Inventory parallel
    class Rec joiner
```

**How it works.** `retrieve_node` runs once, then LangGraph fans out to the
three specialist agents in parallel. Each specialist analyses the *same* retrieved
context through its own lens and writes its finding into shared state. If a
specialist sees red flags it pushes an entry onto the `escalations` reducer
list — the A2A (agent-to-agent) channel. LangGraph waits for all three to
finish before invoking the **Recommendation Agent**, which reads every
specialist's finding plus the full escalation list and produces one prioritised,
explainable plan.

---

## 3. Ingestion pipeline

```mermaid
flowchart LR
    CSV[(supply_chain_data.csv)] --> Load[load_dataframe<br/>+ derived risk fields]
    Load --> Build[build_incident_records<br/>row → narrative + metadata]
    Build --> Chunk[Recursive Semantic Chunking<br/>chunk=600 · overlap=80]
    Chunk --> Emb[Embed<br/>OpenAI text-embed-3-small<br/>fallback MiniLM]
    Emb --> Upsert[Chroma upsert<br/>cosine similarity]
    Upsert --> Done[(Persistent Chroma<br/>./data/chroma_db)]

    Build -. same records .-> BM25[BM25 in-memory index<br/>rebuilt at app startup]
```

**Why per-row narratives?** The source data is structured CSV, but the
retrieval/embedding layer wants language. The data loader converts each row
into a compact prose record that mentions every field (e.g.
*"SKU24 (skincare) supplied by Supplier 2 in Mumbai. Stock level 4 units
(stockout_risk); Inspection Pending; defect rate 3.69%..."*). This makes
both BM25 and semantic search effective without losing structured filters,
which we expose as Chroma metadata.

---

## Component reference

| Module | Path | Responsibility |
| --- | --- | --- |
| Data loader | `app/services/data_loader.py` | CSV → enriched DF → IncidentRecord (narrative + metadata) |
| Chunking | `app/services/chunking.py` | Recursive semantic split (LangChain) |
| Embeddings | `app/services/embeddings.py` | OpenAI primary, SentenceTransformer fallback |
| Vector store | `app/services/vector_store.py` | Chroma persistent + metadata filter |
| BM25 | `app/services/bm25_index.py` | In-memory keyword index + metadata filter |
| Reranker | `app/services/reranker.py` | Lazy-loaded MS-MARCO cross-encoder |
| Retriever | `app/services/retriever.py` | Chroma + BM25 → RRF → rerank |
| Analytics | `app/services/analytics.py` | Deterministic aggregations for dashboard |
| Guardrails | `app/services/guardrails.py` | Input + output validation, PII redaction |
| Agents | `app/agents/{state,nodes,prompts,graph}.py` | LangGraph multi-agent system |
| LLM factory | `app/agents/llm.py` | GPT-4o-mini primary, Groq Llama fallback |
| Tracing | `app/core/tracing.py` | LangSmith env wiring |
| Eval | `backend/scripts/eval.py` + `eval_golden.py` | DeepEval golden test set |

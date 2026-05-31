# Architecture

Four diagrams: **query routing**, **system layers**, **multi-agent flow**, and **ingestion pipeline**.
All Mermaid sources render natively on GitHub and VS Code (Markdown Preview).

---

## 0. Query routing (before LangGraph is invoked)

Every incoming query passes through a layered short-circuit chain. Most simple
queries are resolved instantly without any LLM call.

```mermaid
flowchart TD
    Q([Incoming query]) --> G{Greeting / identity?}
    G -- yes --> GR[Instant greeting reply\nno LLM]
    G -- no --> SC{SCM domain concept?\ne.g. 'what is supply chain risk analysis'}
    SC -- yes --> SR[Canned domain explanation\nno LLM]
    SC -- no --> GK{General knowledge blocker?\ne.g. 'what is blockchain'}
    GK -- yes --> OOS[Out-of-scope reply\nno LLM]
    GK -- no --> GUARD[Guardrails\nPII · injection · scope check]
    GUARD -- fail --> OOS2[Reject / redact]
    GUARD -- pass --> DL{Data-lookup?\ne.g. 'who are our suppliers'}
    DL -- match --> DLR[DataFrame answer\nno LLM]
    DL -- no match --> EC{Exact-match cache hit?}
    EC -- yes --> CR1[Cached response]
    EC -- no --> SEM{Semantic cache hit?}
    SEM -- yes --> CR2[Cached response]
    SEM -- no --> LG[LangGraph multi-agent pipeline]
    LG --> RESP[Full agent response\nstored in both caches]

    classDef fast fill:#dcfce7,stroke:#16a34a
    classDef block fill:#fee2e2,stroke:#dc2626
    classDef llm fill:#ede9fe,stroke:#6d28d9
    class GR,SR,DLR,CR1,CR2 fast
    class OOS,OOS2 block
    class LG,RESP llm
```

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
    Start([Query in]) --> Pre[query_preprocess\nintent · rewrite]
    Pre --> Sup[supervisor_node\nrouting decision]
    Sup --> Ret[retrieve_node\nHybrid RAG]

    Ret --> SA[Supplier Risk Agent\ndefect/inspection lens]
    Ret --> SH[Shipment Analysis Agent\ncarrier/route/delay lens]
    Ret --> IN[Inventory Intelligence\nstockout/overstock lens]

    SA -. A2A escalation .-> Rec
    SH -. A2A escalation .-> Rec
    IN -. A2A escalation .-> Rec

    SA --> Rec[Recommendation Agent\nsynthesize · prioritize · score]
    SH --> Rec
    IN --> Rec

    Rec --> Judge[Judge Agent\nLLM-as-judge quality check]
    Judge --> Rep[Report Agent\npolished narrative]
    Rep --> End([Answer + risk score\n+ sources + escalations])

    classDef parallel fill:#fef3c7,stroke:#b45309
    classDef joiner fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px
    classDef control fill:#f0fdf4,stroke:#16a34a
    class SA,SH,IN parallel
    class Rec joiner
    class Pre,Sup control
```

**How it works.** The query preprocessor rewrites the query and classifies intent.
The supervisor decides which specialist agents to run (and can skip irrelevant ones).
`retrieve_node` runs once, then LangGraph fans out to the three specialist agents
**in parallel** (LangGraph superstep). Each specialist analyses the same retrieved
context through its own lens and writes its finding into shared state. A2A escalation
flags are pushed onto a shared reducer list. The **Recommendation Agent** synthesises
all findings into one prioritised plan. The **Judge Agent** scores the plan against a
quality rubric (actionable, grounded, prioritised, justified). The **Report Agent**
formats a polished narrative (skipped for quick queries per supervisor decision).

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

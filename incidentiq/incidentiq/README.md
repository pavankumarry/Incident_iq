# IncidentIQ
### Real-time AI Co-pilot for Incident Response — Powered by Amazon Bedrock

> **Amazon Bedrock Hackathon 2026** · Reduce MTTR by 44% · Turn 47-minute incidents into 26-minute resolutions

---

## What is IncidentIQ?

IncidentIQ is an autonomous AI engineering platform that watches your code, monitors your services, and acts as a second pair of eyes during incidents. When something breaks — whether from a bad PR, a deployment regression, or a runtime anomaly — IncidentIQ detects it, investigates it, and generates a fix automatically.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INCIDENTIQ PLATFORM                              │
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │  ShopApp UI  │    │ IncidentIQ   │    │   GitHub Repository      │  │
│  │  React :3001 │    │ Dashboard    │    │   pavankumarry/Incident_iq│  │
│  │              │    │ React :3000  │    │                          │  │
│  └──────┬───────┘    └──────┬───────┘    └──────────┬─────────────┘  │
│         │                   │                        │                  │
│         ▼                   ▼                        │ webhook          │
│  ┌──────────────┐    ┌──────────────┐               │                  │
│  │  ShopApp API │    │IncidentIQ API│◄──────────────┘                  │
│  │  FastAPI:8001│    │ FastAPI:8000 │                                   │
│  │  SQLite DB   │    │              │                                   │
│  │  OTEL metrics│───►│  /api/...    │                                   │
│  └──────────────┘    └──────┬───────┘                                   │
│                             │                                            │
│                    ┌────────▼────────┐                                  │
│                    │  LangGraph      │                                   │
│                    │  Orchestrator   │                                   │
│                    │  13-step flow   │                                   │
│                    └────────┬────────┘                                  │
│                             │                                            │
│         ┌───────────────────┼───────────────────┐                       │
│         ▼                   ▼                   ▼                       │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐                │
│  │Observability│   │  RCA Agent   │   │Code Intel.   │                │
│  │   Agent     │   │  Qwen3 32B   │   │   Agent      │                │
│  │  Kimi K2    │   │  DeepSeek V3 │   │ Qwen3 Coder  │                │
│  └─────────────┘   └──────────────┘   └──────────────┘                │
│         │                   │                   │                       │
│         └───────────────────┼───────────────────┘                       │
│                             ▼                                            │
│                    ┌────────────────┐                                   │
│                    │Amazon Bedrock  │                                   │
│                    │P1: Qwen3 32B   │                                   │
│                    │P2: DeepSeek V3 │                                   │
│                    │P3: Qwen3 Coder │                                   │
│                    │P4: Kimi K2     │                                   │
│                    │EMB: Titan V2   │                                   │
│                    └────────┬───────┘                                   │
│                             │                                            │
│                    ┌────────▼───────┐                                   │
│                    │  ChromaDB      │                                   │
│                    │  Vector Store  │                                   │
│                    │  1200+ incident│                                   │
│                    │  embeddings    │                                   │
│                    └────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Flow 1 — PR Review (GitHub Integration)

```mermaid
flowchart TD
    A([👨‍💻 Developer pushes a PR]) --> B[GitHub sends webhook\nPOST /api/github/webhook]
    B --> C[Fetch diff from GitHub API\nget changed files + patches]
    C --> D[Detect affected service\nfrom file paths]
    D --> E[Pull live OTEL metrics\nfor that service]
    E --> F{Code review\nQwen3 Coder P3}
    F --> G[Analyze diff for:\n• Bugs & logic errors\n• SQL injection\n• Resource leaks\n• Missing timeouts\n• Security issues]
    G --> H{Risk validation\nDeepSeek V3 P2}
    H --> I[Correlate with\nlive OTEL telemetry]
    I --> J{Risk Level?}
    J -->|LOW| K[✅ APPROVE PR\nPost review comment]
    J -->|MEDIUM/HIGH| L[⚠️ REQUEST CHANGES\nPost detailed review]
    J -->|CRITICAL| M[🚨 REQUEST CHANGES\n+ Trigger incident workflow]
    M --> N[Full 13-step RCA\nautomatically started]
    K --> O([Review posted to GitHub PR])
    L --> O
    N --> O

    style A fill:#1e3a5f,color:#fff
    style O fill:#1e5f3a,color:#fff
    style K fill:#1a4a2e,color:#fff
    style L fill:#4a3a1a,color:#fff
    style M fill:#4a1a1a,color:#fff
```

---

## Flow 2 — Incident Detection & RCA (13-Step Workflow)

```mermaid
flowchart TD
    A([🔴 Anomaly Detected]) --> B

    subgraph STEP1["Steps 1-2: Collect & Detect"]
        B[Collect telemetry\nlogs, traces, metrics] --> C[ObservabilityAgent\ndetects anomalies\nKimi K2 fast classification]
    end

    subgraph STEP2["Steps 3-5: Investigate"]
        C --> D[Retrieve similar incidents\nTitan Embeddings V2\nChromaDB semantic search]
        D --> E[Generate root cause\nhypotheses\nQwen3 32B deep reasoning]
        E --> F[Validate hypotheses\nDeepSeek V3\nconsensus check]
    end

    subgraph STEP3["Steps 6-8: Analyze"]
        F --> G[Analyze repository\ncode context\naffected services]
        G --> H[Generate remediation\noptions]
        H --> I[Simulate potential\noutcomes]
    end

    subgraph STEP4["Steps 9-11: Fix"]
        I --> J[Generate code fix\nQwen3 Coder P3]
        J --> K[Run validation pipeline\nstatic analysis, security scan\nlint, type check]
        K --> L[Generate Pull Request\nwith full context]
    end

    subgraph STEP5["Steps 12-13: Deploy"]
        L --> M{Requires human\napproval?}
        M -->|YES| N[⚠️ Await approval\nPOST /api/approval]
        M -->|NO| O[Auto-proceed]
        N --> P[Monitor post-deploy\nimpact]
        O --> P
    end

    P --> Q([✅ Incident Resolved])

    style A fill:#4a1a1a,color:#fff
    style Q fill:#1a4a2e,color:#fff
```

---

## Flow 3 — Live Copilot (Real-time Assistance)

```mermaid
flowchart LR
    A([Incident starts]) --> B[Start copilot session\nPOST /api/copilot/start]
    B --> C[Engineer sends updates\nSlack messages, actions taken]
    C --> D{Rate limit check\nmax 1 per 5 min}
    D -->|Too soon| C
    D -->|OK| E[Analyze incident state\nKimi K2 fast response]
    E --> F[Search vector store\nfor similar incidents]
    F --> G[Check SOP gaps\ndetect missing steps]
    G --> H{Confidence\n≥ 70%?}
    H -->|NO| C
    H -->|YES| I[🤖 Interject with insight\nevidence + command + outcome]
    I --> C
    C --> J{Incident resolved?}
    J -->|NO| C
    J -->|YES| K[Generate postmortem\nQwen3 32B]
    K --> L([📄 Postmortem ready])

    style A fill:#1e3a5f,color:#fff
    style L fill:#1a4a2e,color:#fff
    style I fill:#2a4a1a,color:#fff
```

---

## Flow 4 — ShopApp Demo (End-to-End)

```mermaid
flowchart TD
    A([🛒 ShopApp running\nclean v1.0.0]) --> B[Generate clean traffic\n0% error rate ✅]
    B --> C[Developer merges\nbuggy PR v1.1.0]
    C --> D[Bugs introduced:\n• Connection leak in sessions.py\n• SQL injection in products.py\n• No timeout in orders.py]
    D --> E[Traffic hits buggy endpoints\nerror rate spikes to 25%]
    E --> F{Two paths}

    F --> G[PATH A: GitHub Webhook\nPR auto-review catches bugs\nbefore merge]
    F --> H[PATH B: Runtime detection\nOTEL metrics spike\nwatch_and_alert.py detects]

    G --> I[IncidentIQ posts\nREQUEST CHANGES review\nto GitHub PR]
    H --> J[Auto-sends to IncidentIQ\nPOST /api/incident/investigate]

    J --> K[13-step RCA workflow\n98% confidence hypothesis:\nconnection pool exhaustion\nfrom v1.1.0 deployment]
    K --> L[PR generated:\nfix connection leaks\nparameterize SQL queries\nadd timeouts]
    L --> M[Clean files restored\nfrom .bak backups]
    M --> N[Traffic normalizes\n0% error rate ✅]

    I --> O([🔒 Bug blocked before production])
    N --> P([✅ Service recovered])

    style A fill:#1e3a5f,color:#fff
    style C fill:#4a1a1a,color:#fff
    style D fill:#4a1a1a,color:#fff
    style O fill:#1a4a2e,color:#fff
    style P fill:#1a4a2e,color:#fff
```

---

## Flow 5 — Multi-Model Consensus

```mermaid
flowchart LR
    A([Incident input]) --> B

    subgraph MODELS["Amazon Bedrock Model Stack"]
        B[P4: Kimi K2\nFast classification\nAlert triage] --> C
        C[P1: Qwen3 32B\nDeep RCA reasoning\nHypothesis generation] --> D
        D[EMB: Titan V2\nVector embeddings\nSimilar incident search] --> E
        E[P2: DeepSeek V3\nHypothesis validation\nRisk assessment] --> F
        F{P0/P1 severity?}
        F -->|YES| G[P2: DeepSeek V3\nFinal critical\nvalidation]
        F -->|NO| H
        G --> H
    end

    subgraph GATE["Confidence Gate"]
        H[Aggregate confidence\nscore] --> I{Score ≥ 0.70?}
        I -->|NO| J[🔇 Suppress\nsuggestion]
        I -->|YES| K[P3: Qwen3 Coder\nGenerate code fix\n+ PR]
    end

    K --> L([✅ Validated suggestion\nor PR shown to engineer])

    style A fill:#1e3a5f,color:#fff
    style J fill:#4a1a1a,color:#fff
    style L fill:#1a4a2e,color:#fff
```

---

## Model Priority Stack

| Priority | Model | Role | Tasks |
|----------|-------|------|-------|
| **P1** | `qwen.qwen3-32b-v1:0` | Primary Reasoning | RCA, orchestration, deep analysis |
| **P2** | `deepseek.v3-v1:0` | Deep Analysis | Critical validation, consensus |
| **P3** | `qwen.qwen3-coder-30b-a3b-v1:0` | Code Intelligence | PR generation, code review, fixes |
| **P4** | `moonshotai.kimi-k2.5` | Fast ChatOps | Alert classification, summaries |
| **EMB** | `amazon.titan-embed-text-v2:0` | Embeddings | Vector search, RAG retrieval |

---

## Guardrail System

```mermaid
flowchart TD
    A([Any AI action]) --> B[Guardrail Agent checks]
    B --> C{Secret leakage\ndetected?}
    C -->|YES| D[🚫 BLOCK — credentials\nin output]
    C -->|NO| E{Prompt injection\ndetected?}
    E -->|YES| F[🚫 BLOCK — malicious\ninput sanitized]
    E -->|NO| G{Confidence\n≥ 0.70?}
    G -->|NO| H[🔇 SUPPRESS — low\nconfidence output]
    G -->|YES| I{Requires human\napproval?}
    I -->|YES — production deploy\nschema change, infra delete| J[⚠️ HOLD — await\nhuman approval]
    I -->|NO| K[✅ ALLOW — action\nproceeds]
    J --> L{Approved?}
    L -->|YES| K
    L -->|NO| M[🚫 BLOCK — rejected\nby reviewer]
    K --> N[📝 Audit log written]
    D --> N
    F --> N
    H --> N
    M --> N

    style D fill:#4a1a1a,color:#fff
    style F fill:#4a1a1a,color:#fff
    style H fill:#3a3a1a,color:#fff
    style J fill:#4a3a1a,color:#fff
    style K fill:#1a4a2e,color:#fff
    style M fill:#4a1a1a,color:#fff
```

---

## Quick Start

```powershell
# Terminal 1 — IncidentIQ backend
cd C:\grabhack\incidentiq
$env:PYTHONPATH = "C:\grabhack\incidentiq"
C:\grabhack\venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000 --reload

# Terminal 2 — ShopApp backend
cd C:\grabhack\shopapp\backend
C:\grabhack\venv\Scripts\python.exe -m uvicorn main:app --port 8001 --reload

# Terminal 3 — IncidentIQ dashboard
cd C:\grabhack\incidentiq\frontend
npm run dev   # http://localhost:3000

# Terminal 4 — ShopApp frontend
cd C:\grabhack\shopapp\frontend
npm run dev   # http://localhost:3001

# Run the full end-to-end demo
cd C:\grabhack\shopapp
C:\grabhack\venv\Scripts\python.exe scripts\run_demo.py
```

---

## Services

| Service | URL | Description |
|---------|-----|-------------|
| ShopApp UI | http://localhost:3001 | E-commerce demo app |
| ShopApp API | http://localhost:8001 | FastAPI + SQLite |
| IncidentIQ UI | http://localhost:3000 | AI dashboard |
| IncidentIQ API | http://localhost:8000 | FastAPI multi-agent |
| API Docs | http://localhost:8000/docs | Swagger UI |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI/LLM | Amazon Bedrock (Qwen3, DeepSeek, Kimi, Titan) |
| Orchestration | LangGraph, LangChain |
| Backend | Python 3.13, FastAPI, WebSockets |
| Vector DB | ChromaDB (dev) / Pinecone (prod) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Cache | Redis |
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
| Observability | OpenTelemetry, Prometheus, CloudWatch |
| Containers | Docker, Kubernetes |

---

## Repository Structure

```
Incident_iq/
├── incidentiq/                  # AI Incident Response Platform
│   ├── backend/
│   │   ├── agents/              # 5 specialized AI agents
│   │   │   ├── observability_agent.py
│   │   │   ├── rca_agent.py
│   │   │   ├── code_intelligence_agent.py
│   │   │   ├── incident_copilot_agent.py
│   │   │   └── orchestrator.py
│   │   ├── bedrock/             # Bedrock client + model router
│   │   ├── integrations/        # GitHub webhook + OTEL collector
│   │   ├── memory/              # Vector store + incident seeding
│   │   ├── validators/          # Guardrail agent
│   │   ├── config.py
│   │   └── main.py              # FastAPI app (:8000)
│   ├── frontend/                # React dashboard (:3000)
│   │   └── src/pages/
│   │       ├── Dashboard.tsx    # Live service health
│   │       ├── PRReview.tsx     # GitHub PR analysis
│   │       ├── IncidentInvestigate.tsx
│   │       ├── LiveCopilot.tsx  # Real-time copilot
│   │       └── ReasoningLog.tsx # Audit trail
│   └── scripts/
│       ├── test_bedrock.py      # Verify all 5 models
│       ├── test_pr_review.py    # PR review demo
│       └── run_demo.py          # Full demo
│
└── shopapp/                     # Demo E-commerce Target App
    ├── backend/
    │   ├── routes/              # products, orders, users, sessions
    │   ├── models.py
    │   ├── telemetry.py         # OTEL instrumentation
    │   └── main.py              # FastAPI app (:8001)
    ├── frontend/                # React shop (:3001)
    └── scripts/
        ├── introduce_bug.py     # Inject 3 realistic bugs
        ├── fix_bug.py           # Restore clean files
        ├── notify_incidentiq.py # Send to IncidentIQ manually
        ├── watch_and_alert.py   # Continuous OTEL watcher
        └── run_demo.py          # Full end-to-end demo
```

---

*Built for the Amazon Bedrock Hackathon 2026 — IncidentIQ: Real-time AI co-pilot for incident response.*

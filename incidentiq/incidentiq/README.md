# IncidentIQ
**Real-time AI co-pilot for incident response — powered by Amazon Bedrock**

> Reduce MTTR by 44%. Turn 47-minute incidents into 26-minute resolutions.

---

## Problem Statement

Modern engineering teams face three compounding problems during incidents:

1. **Tribal knowledge bottleneck** — critical context lives in the heads of senior engineers who may not be available at 3am.
2. **Slow root cause analysis** — correlating logs, metrics, traces, and deployment history manually takes 20-40 minutes before mitigation even begins.
3. **Cognitive overload** — during high-severity incidents, engineers juggle Slack threads, dashboards, runbooks, and code simultaneously, leading to missed steps and delayed recovery.

IncidentIQ solves all three by acting as an always-available AI second pair of eyes embedded directly into incident workflows.

---

## Solution

IncidentIQ is a multi-agent AI platform that:

- **Watches** Slack threads, PagerDuty alerts, logs, metrics, and Kubernetes events in real time
- **Retrieves** similar historical incidents from a semantic vector store (1,200+ embeddings)
- **Reasons** autonomously using a 13-step investigation workflow
- **Interjects** with high-confidence, evidence-backed recommendations — only when confidence ≥ 0.70
- **Generates** code fixes and Pull Requests automatically
- **Drafts** postmortems and RCA documents after resolution

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│         Incident Timeline UI │ PR Review UI │ Copilot Chat       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI Gateway (:8000)                        │
│              /api/incident  /api/copilot  /ws/incident            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   LangGraph Orchestrator                          │
│              13-Step Reasoning Workflow Engine                    │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│Obs.  │ │ RCA   │ │ Code   │ │Copilot │ │Guardrail │
│Agent │ │Agent  │ │Agent   │ │Agent   │ │Agent     │
└──┬───┘ └───┬───┘ └───┬────┘ └───┬────┘ └────┬─────┘
   │         │         │          │            │
   └─────────┴─────────┴──────────┴────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│                   Amazon Bedrock                                  │
│  Claude 3.7 Sonnet │ Claude Opus │ Nova Pro │ Nova Lite │ Llama  │
│                    Titan Embeddings V2                            │
└───────────────────────┬─────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│                    Memory & Storage Layer                         │
│   ChromaDB/Pinecone (vectors) │ Redis (state) │ PostgreSQL (DB)  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Multi-Agent System

| Agent | Model | Responsibility |
|-------|-------|----------------|
| **Observability Agent** | Nova Lite | Monitors telemetry, detects anomalies via statistical + LLM analysis |
| **RCA Agent** | Claude 3.7 Sonnet | Autonomous root cause investigation with causal inference |
| **Code Intelligence Agent** | Claude 3.7 Sonnet | Generates code fixes, tests, and Pull Requests |
| **Incident Copilot Agent** | Nova Pro | Real-time guidance, SOP gap detection, smart interjections |
| **Guardrail Agent** | Deterministic | Policy enforcement, secret detection, confidence gating |
| **Knowledge Retrieval** | Titan Embeddings V2 | Semantic search over 1,200+ historical incidents |

### Multi-Model Consensus Workflow
```
Nova Lite → classifies incident type
    ↓
Claude Sonnet → deep RCA reasoning
    ↓
Titan Embeddings → retrieves similar incidents
    ↓
Llama 3.1 70B → validates hypothesis
    ↓
Claude Opus → final validation (P0/P1 only)
    ↓
Guardrail Agent → confidence gate (≥0.70)
    ↓
Engineer suggestion or PR generation
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI/LLM** | Amazon Bedrock (Claude, Nova, Titan, Llama) |
| **Orchestration** | LangGraph, LangChain |
| **Backend** | Python, FastAPI, WebSockets |
| **Task Queue** | Celery + Redis |
| **Vector DB** | ChromaDB (dev) / Pinecone (prod) |
| **Database** | PostgreSQL |
| **Cache/State** | Redis |
| **Containers** | Docker, Kubernetes |
| **Observability** | Prometheus, Grafana, OpenTelemetry, CloudWatch |
| **CI/CD** | GitHub Actions |
| **IaC** | Terraform |

---

## Guardrails

IncidentIQ operates in **advisory-only mode by default**. It recommends, explains, and generates — but never autonomously deploys or deletes.

### Confidence Gate
Every AI recommendation is suppressed unless confidence ≥ 0.70. This prevents low-quality suggestions from adding noise during high-stress incidents.

### Human Approval Required For
- Production deployments
- Database schema changes
- Infrastructure deletion
- Permission changes
- Any customer-impacting action

### Hard Guardrails (Cannot Be Bypassed)
- Secret leakage detection — scans all outputs for credential patterns
- Prompt injection detection — sanitizes all user input before LLM processing
- No autonomous destructive actions
- Full audit log for every agent action

### Hallucination Prevention
- Multi-model consensus (Claude + Llama validation)
- Deterministic validators before any suggestion is shown
- Citations required from telemetry data
- Unverifiable conclusions rejected

---

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- AWS credentials with Bedrock access (Claude, Nova, Titan, Llama models enabled)

### 1. Clone and configure
```bash
git clone <repo>
cd incidentiq
cp .env.example .env
# Edit .env with your AWS credentials and config
```

### 2. Start with Docker Compose
```bash
docker-compose up -d
```

### 3. Seed historical incidents
```bash
docker-compose exec api python -m backend.memory.seed_incidents
```

### 4. Run the demo scenario
```bash
curl -X POST http://localhost:8000/api/demo/run | python -m json.tool
```

### 5. View API docs
Open http://localhost:8000/docs

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/telemetry/analyze` | Analyze telemetry for anomalies |
| `POST` | `/api/incident/investigate` | Full 13-step investigation workflow |
| `POST` | `/api/copilot/start` | Start real-time copilot tracking |
| `POST` | `/api/copilot/update` | Send incident update, receive interjection |
| `GET` | `/api/copilot/{id}/summary` | Live incident summary |
| `POST` | `/api/copilot/{id}/postmortem` | Generate postmortem document |
| `POST` | `/api/approval` | Submit human approval decision |
| `WS` | `/ws/incident/{id}` | Real-time WebSocket streaming |
| `POST` | `/api/demo/run` | Run hackathon demo scenario |

---

## Demo Scenario

The demo simulates a real-world P1 incident:

1. **Payment service** experiences 8.2s p99 latency (normal: 120ms)
2. **ObservabilityAgent** detects the anomaly (confidence: 0.92)
3. **RCAAgent** correlates with deployment v2.4.1 and retrieves INC-2024-0311 (91% similarity)
4. **KnowledgeAgent** surfaces: *"Redis connection pool exhaustion — similar to March 2024 incident"*
5. **CodeAgent** identifies the bug: connection not released on exception path
6. **ValidationAgent** benchmarks the fix: reduces connection leak by 100%
7. **PR generated**: `fix(payment-service): release DB connection in finally block`
8. **CopilotAgent** interjects: *"SOP Step 3 (Redis pool verification) has not been executed"*
9. **Postmortem** auto-drafted after resolution

---

## Reasoning Log Format

Every workflow produces an explainable reasoning log:

```
[ObservabilityAgent] Detected elevated API latency on payment-service (p99=8200ms)
[RCAAgent] Starting investigation for INC-20260516100001 on payment-service
[RCAAgent] Retrieving similar historical incidents via RAG...
[RCAAgent] Found 3 similar incidents. Top match: INC-2024-0311 (91% similarity)
[RCAAgent] Deployment correlation: CORRELATED: v2.4.1 - session handler exception path
[RCAAgent] Top hypothesis: 'Connection leak in session_manager.py' (confidence=0.89)
[KnowledgeAgent] Similar incident: INC-2024-0311 (91% similarity)
[CodeAgent] Generated fix for payment_service/session_manager.py (risk=low)
[CodeAgent] PR generated: 'fix(payment-service): release DB connection in finally block' (confidence=0.85)
[GuardrailAgent] Human approval required before deployment
```

---

## Future Scope

- **Autonomous remediation** — self-healing with circuit breaker auto-configuration
- **Predictive scaling** — ML-based capacity forecasting before incidents occur
- **Self-healing infrastructure** — Terraform drift detection and auto-correction
- **AI SRE copilots** — specialized agents per domain (database, networking, security)
- **Multi-cloud support** — Azure Monitor, GCP Cloud Operations integration
- **Chaos engineering integration** — proactive resilience testing with AI-generated scenarios

---

## Security Notice

Never hardcode AWS credentials. Always use environment variables or IAM roles.

```bash
# Safe — environment variables
export AWS_DEFAULT_REGION="us-west-2"
export AWS_ACCESS_KEY_ID="<AWS_ACCESS_KEY_ID>"
export AWS_SECRET_ACCESS_KEY="<AWS_SECRET_ACCESS_KEY>"
export AWS_SESSION_TOKEN="<AWS_SESSION_TOKEN>"
```

If credentials were previously exposed, rotate them immediately via AWS IAM.

---

*Built for the Amazon Bedrock Hackathon — IncidentIQ: Real-time AI co-pilot for incident response.*

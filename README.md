# India Tax Research Agent

AI-powered Indian Direct Tax research using AutoGen v0.4+, Qdrant, and BAAI/bge-large-en-v1.5.

## Architecture
User Query
|
UserProxyAgent (session management, follow-up detection)
|
RetrievalAgent (embed + vector search + reranking)
|
CitationValidationAgent (synthesis + citation verification)
|
Structured Response 
## Agents

**UserProxyAgent** — Manages sessions, detects follow-up queries using keyword matching, enriches context for multi-turn conversations (DT-10), presents final validated response.

**RetrievalAgent** — Embeds query using BAAI/bge-large-en-v1.5, applies metadata filters (section number, circular number), searches Qdrant top-10, re-ranks with cross-encoder ms-marco-MiniLM-L-6-v2, returns top-5 chunks with full metadata.

**CitationValidationAgent** — Synthesizes answer from retrieved chunks only, calls verify_citations tool which does direct Qdrant scroll by section number, assigns HIGH/MEDIUM/LOW confidence, flags unverified citations before response reaches user.

## Stack

| Layer | Choice |
|---|---|
| Agent Framework | AutoGen v0.4+ |
| LLM | Groq llama-3.3-70b-versatile |
| Embeddings | BAAI/bge-large-en-v1.5 (local, cached) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 (local, cached) |
| Vector Store | Qdrant Cloud |
| Backend | FastAPI (Python) |
| Frontend | Next.js 14 + React |


cd tax-research-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in QDRANT_URL, QDRANT_API_KEY, GROQ_API_KEY
```

## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesti## Ingesbed_and_index.py
```

## Running

```bash
# Terminal 1 - Backend
source venv/bin/activate
uvicorn backend.api.main:app --port 8000 --workers 1

# Terminal 2 - Frontend
cd frontend && npm install && npm run dev
```

Visit http://localhost:3000

## Environment Variables
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=tax_research
GROQ_API_KEY=
## ITA 2025 Section Renumbering

The Income Tax Act 2025 renumbered all sections from the 1961 Act.

| Old (1961) | New (2025) |
|---|---|
| 80C | 123 |
| 2(22)(e) | 2(40)(e) |
| 147 | 279 |
| 148 | 280 |
| 260A | 365 |
| 54 / 54F | 86 |
| 68 | 101 |
| 70 / 71 / 74 | 109 / 110 / 113 |

## Latency Report

| Query | Total (ms) | Confidence | Citations |
|---|---|---|---|
| DT-01 Section 54 | 28567 | HIGH | 4 verified |
| DT-02 Section 80C | 22815 | HIGH | 2 verified |
| DT-03 Capital Loss | 62420 | HIGH | 6 verified |
| DT-04 54 vs 54F | 26119 | HIGH | 3 verified |
| DT-05 Deemed Dividend | 12317 | HIGH | 1 verified |

Cold-start P50 ~25s (reranker loading). Warm P50 ~8s. P95 <15s on warm queries.

## Input Sanitisation

All queries pass through `sanitize_query()` in `backend/api/main.py` before entering the pipeline. It strips queries over 2000 characters and detects prompt injection patterns such as "ignore previous instructions", "you are now", and "system prompt", replacing them with `[INPUT_FILTERED]`. System and user message namespaces aAll queries pass through `sanitize_query()` in `backend/api/mainset All queries pass throug inclAll raw usAll querie
## Agent Traces

See `traces/agent_traces.json` for full I/O chains for DT-02, DT-03, and DT-05 (required by assignment).

"""
FastAPI backend — document Section 5 specifies FastAPI (Python).

Endpoints:
- POST /query — main query endpoint
- GET /session/{session_id} — retrieve conversation history
- GET /health — health check
"""

import os
import sys
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.orchestrator import run_pipeline, session_store

app = FastAPI(
    title="India Tax Research Agent",
    description="AI-powered Indian Direct Tax research using AutoGen v0.4+",
    version="1.0.0"
)

# CORS — allow Next.js frontend (document specifies Next.js 14)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------
# Input sanitization — document Section 12 requires this
# and requires documentation in README
# ----------------------------------------------------------------

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "ignore your instructions",
    "you are now",
    "disregard your",
    "forget everything",
    "forget your instructions",
    "[system]",
    "<system>",
    "###instruction",
    "system prompt",
    "new instructions",
    "override instructions",
]


def sanitize_query(query: str) -> str:
    """
    Sanitize user input to prevent prompt injection.
    Document Section 12: 'Apply strict input sanitisation on all user-submitted queries.
    System and user message namespaces in LLM calls must be kept separate.'
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Enforce length limit
    query = query[:2000]

    # Detect and neutralize injection attempts
    query_lower = query.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in query_lower:
            # Replace the pattern rather than reject the whole query
            query = query.lower().replace(pattern, "[INPUT_FILTERED]")

    return query.strip()


# ----------------------------------------------------------------
# Request / Response models
# ----------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    session_id: str = None


class LatencyBreakdown(BaseModel):
    retrieval: float
    synthesis: float
    citation_validation: float
    total: float


class QueryResponse(BaseModel):
    session_id: str
    turn: int
    query: str
    response: str
    citations: list
    overall_confidence: str
    unverified_count: int
    chunks_retrieved: int
    latency_ms: dict


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "India Tax Research Agent is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    """
    Main query endpoint.
    Accepts a natural-language Indian tax research question.
    Returns a structured, citation-verified answer.

    The pipeline:
    UserProxyAgent → RetrievalAgent → LLM Synthesis → CitationValidationAgent
    """
    sanitized = sanitize_query(request.query)
    session_id = request.session_id or str(uuid.uuid4())

    try:
        result = run_pipeline(sanitized, session_id=session_id)
        return QueryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.get("/session/{session_id}")
def get_session_history(session_id: str):
    """Return conversation history for a session (for multi-turn DT-10 test)."""
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_store[session_id]

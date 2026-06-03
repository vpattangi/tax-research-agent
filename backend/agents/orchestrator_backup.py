import json
import time
import uuid
import ollama

from .retrieval_tool import retrieve_chunks
from .citation_tool import validate_citations

session_store = {}


def call_ollama(prompt: str) -> str:
    response = ollama.chat(
        model="llama3:8b",
        messages=[{"role": "user", "content": prompt}]
    )
    return response["message"]["content"]


def get_context(query: str) -> str:
    chunks = retrieve_chunks(query, top_k=2)

    formatted = []
    for c in chunks:
        formatted.append(
            f"[{c.get('id')}] {c.get('section')}:\n{c.get('text')}"
        )

    return "\n\n".join(formatted)


def build_prompt(query: str, context: str) -> str:
    return f"""
You are a tax law assistant.

STRICT RULES:
- Use ONLY the provided context
- Do NOT hallucinate
- If missing info, say so

Context:
{context}

Question:
{query}

FORMAT:

## Final Answer
...

## Legal Reasoning
...

## Supporting References
...

## Confidence & Disclaimer
...
"""


def run_pipeline(query: str, session_id: str = None):
    start = time.time()

    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id not in session_store:
        session_store[session_id] = {"history": []}

    # 1. Retrieval
    context = get_context(query)

    # 2. LLM
    prompt = build_prompt(query, context)
    response = call_ollama(prompt)

    # 3. Citation validation
    try:
        citation_json = json.loads(validate_citations(response))
    except:
        citation_json = {}

    # Save history
    session_store[session_id]["history"].append({
        "query": query,
        "response": response[:200]
    })

    return {
        "session_id": session_id,
        "response": response,
        "citations": citation_json.get("citations", []),
        "confidence": citation_json.get("overall_confidence", "LOW"),
        "latency_ms": int((time.time() - start) * 1000)
    }

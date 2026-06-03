"""
Retrieval tool used by RetrievalAgent.

Document Section 3 — RetrievalAgent responsibilities:
- Embed the incoming query and perform similarity search
- Return top-k chunks with full source metadata
- Apply metadata pre-filters (section number, circular number, domain)
- Apply cross-encoder re-ranking on top-20 candidates to select final top-5

Document Section 5 specifies:
- Embeddings: BAAI/bge-large-en-v1.5
- Vector Store: Qdrant with metadata filtering
- Hybrid Search: BM25s Python library (document-specified)
"""

import os
import re
import time
import json
import bm25s
import numpy as np
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "tax_research")
EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_CACHE = "models/embeddings"
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_CACHE_PATH = "models/reranker"

SECTION_MAP = {
    "80C": "123", "2(22)(e)": "2", "147": "279", "148": "280",
    "260A": "365", "54": "86", "54F": "86", "68": "101",
    "70": "109", "71": "110", "74": "113"
}

def translate_section(s):
    t = SECTION_MAP.get(s.strip(), s.strip())
    if t != s.strip():
        print("[RetrievalTool] " + s + " -> " + t)
    return t


_embedding_model = None
_reranker_model = None
_qdrant_client = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        os.makedirs(EMBEDDING_CACHE, exist_ok=True)
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            cache_folder=EMBEDDING_CACHE
        )
    return _embedding_model


def get_reranker():
    global _reranker_model
    if _reranker_model is None:
        print("[RetrievalTool] Loading reranker (one-time)...")
        os.makedirs(RERANKER_CACHE_PATH, exist_ok=True)
        os.environ["TRANSFORMERS_CACHE"] = RERANKER_CACHE_PATH
        os.environ["HF_HOME"] = RERANKER_CACHE_PATH
        # Load from local cache if available, else download
        local_path = os.path.join(RERANKER_CACHE_PATH, "saved_model")
        if os.path.exists(local_path):
            print("[RetrievalTool] Loading reranker from local cache...")
            _reranker_model = CrossEncoder(local_path, max_length=512)
        else:
            print("[RetrievalTool] Downloading reranker (first time only)...")
            _reranker_model = CrossEncoder(RERANKER_MODEL_NAME, max_length=512)
            _reranker_model.save(local_path)
            print("[RetrievalTool] Reranker saved to local cache")
    return _reranker_model


def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _qdrant_client


# Pre-warm both models at import time in background threads
import threading
threading.Thread(target=get_embedding_model, daemon=True).start()
threading.Thread(target=get_reranker, daemon=True).start()


def embed_query(query: str) -> list:
    model = get_embedding_model()
    prefixed = f"Represent this sentence for searching relevant passages: {query}"
    vector = model.encode(prefixed, normalize_embeddings=True)
    return vector.tolist()


def detect_metadata_filters(query: str) -> dict:
    filters = {}
    section_match = re.search(r'[Ss]ection\s+(\d+[A-Z]?)', query)
    if section_match:
        filters["section"] = translate_section(section_match.group(1))
    circ_match = re.search(r'Circular\s+(?:No\.?\s*)?(\d+)', query, re.IGNORECASE)
    if circ_match:
        filters["circular_number"] = circ_match.group(1)
    return filters


def retrieve_chunks(query: str, top_k: int = 5) -> dict:
    retrieval_start = time.time()
    client = get_qdrant_client()

    # Step 1: Embed query
    query_vector = embed_query(query)

    # Step 2: Detect metadata filters
    filters = detect_metadata_filters(query)
    print(f"[RetrievalTool] Metadata filters detected: {filters}")

    # Step 3: Build Qdrant filter if needed
    qdrant_filter = None
    if filters:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
        ]
        qdrant_filter = Filter(must=conditions)

    # Step 4: Vector search — top 10 (reduced from 20 for speed)
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=10,
        query_filter=qdrant_filter,
        with_payload=True
    ).points

    vector_retrieval_time = (time.time() - retrieval_start) * 1000
    print(f"[RetrievalTool] Vector retrieval time: {vector_retrieval_time:.0f}ms (target: <800ms)")
    if vector_retrieval_time > 800:
        print(f"[RetrievalTool] WARNING: Retrieval exceeded 800ms target")

    if not results:
        return {
            "query": query,
            "chunks": [],
            "retrieval_time_ms": vector_retrieval_time,
            "chunk_count": 0
        }

    # Step 5: Cross-encoder re-ranking — top 10 -> top_k
    reranker = get_reranker()
    candidate_texts = [r.payload.get("text", "") for r in results]
    rerank_scores = reranker.predict([(query, text) for text in candidate_texts])

    ranked = sorted(
        zip(rerank_scores, results),
        key=lambda x: x[0],
        reverse=True
    )
    top_results = ranked[:top_k]

    chunks = []
    for rerank_score, result in top_results:
        payload = result.payload
        vector_score = result.score if hasattr(result, "score") else 0.0
        chunks.append({
            "chunk_id": payload.get("chunk_id", "unknown"),
            "text": payload.get("text", ""),
            "rerank_score": float(rerank_score),
            "vector_score": float(vector_score),
            "metadata": {
                k: v for k, v in payload.items()
                if k not in ["chunk_id", "text"]
            }
        })

    total_retrieval_time = (time.time() - retrieval_start) * 1000

    return {
        "query": query,
        "chunks": chunks,
        "retrieval_time_ms": total_retrieval_time,
        "vector_search_time_ms": vector_retrieval_time,
        "chunk_count": len(chunks),
        "filters_applied": filters
    }
"""
Citation validation tool used by CitationValidationAgent.

Document Section 3 — CitationValidationAgent responsibilities:
- Parse generated response and extract every legal citation
- Verify section numbers exist in indexed corpus → flag Unverified if not
- Verify circular/notification references match indexed metadata
- Assign confidence: HIGH (chunk retrieved and matched), MEDIUM (partial), LOW (not retrievable)
- Remove or explicitly mark citations not traceable to a retrieved chunk

Required output schema from document Section 3:
{
  "citations": [
    {
      "text": "Section 2(22)(e), Income Tax Act, 2025",
      "type": "act",
      "verified": true,
      "confidence": 0.97,
      "source_chunk_id": "ITA_2025_S2_22e"
    }
  ],
  "overall_confidence": "HIGH",
  "unverified_count": 0
}
"""

import re
import os
import time
import json
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "tax_research")
EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"

_model = None
SECTION_MAP={"80C":"123","2(22)(e)":"2","147":"279","148":"280","260A":"365","54":"86","54F":"86","68":"101","70":"109","71":"110","74":"113"}
def translate_sec(s):
    return SECTION_MAP.get(s.strip(),s.strip())

_client = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _client


def extract_citations(response_text: str) -> list:
    """
    Parse response text and extract all legal citations.
    Document requires scanning for: section numbers, circular numbers, case names.
    """
    citations = []
    seen = set()

    # Pattern 1: Section references
    # Handles: Section 54, Section 2(22)(e), Section 80C, Section 54F
    section_pattern = re.compile(
        r'[Ss]ection\s+(\d+[A-Z]?(?:\(\d+\))?(?:\([a-zA-Z]\))?(?:\([ivx]+\))?)',
    )
    for match in section_pattern.finditer(response_text):
        raw = match.group(1)
        text = f"Section {raw}, Income Tax Act, 2025"
        if text not in seen:
            seen.add(text)
            citations.append({
                "text": text,
                "type": "act",
                "raw_ref": raw,
                "section_num": re.match(r'(\d+[A-Z]?)', raw).group(1)
            })

    # Pattern 2: CBDT Circulars
    circ_pattern = re.compile(
        r'CBDT\s+Circular\s+(?:No\.?\s*)?(\d+(?:[/\-]\d+)?(?:/\d{4})?)',
        re.IGNORECASE
    )
    for match in circ_pattern.finditer(response_text):
        raw = match.group(1)
        text = f"CBDT Circular No. {raw}"
        if text not in seen:
            seen.add(text)
            citations.append({
                "text": text,
                "type": "circular",
                "raw_ref": raw
            })

    # Pattern 3: Case law — "Name vs Name" or "Name v. Name"
    case_pattern = re.compile(
        r'([A-Z][A-Za-z\s\.]+(?:Ltd|Pvt|Co|Inc|Corp|CIT|ITO|ACIT|ITAT|SC|HC)?\.?\s+(?:vs?\.?|v/s)\s+[A-Z][A-Za-z\s\.]+(?:Ltd|Pvt|Co|Inc|Corp|CIT|ITO|ACIT|ITAT|SC|HC)?\.?)',
    )
    for match in case_pattern.finditer(response_text):
        text = match.group(0).strip()
        # Filter out very short or very long matches
        if 10 < len(text) < 100 and text not in seen:
            seen.add(text)
            citations.append({
                "text": text,
                "type": "case_law",
                "raw_ref": text
            })

    return citations


def verify_single_citation(citation: dict, client: QdrantClient, model: SentenceTransformer) -> dict:
    """
    Verify one citation against the Qdrant index.
    Returns citation with: verified (bool), confidence (float), source_chunk_id (str|None)
    """
    try:
        query_vector = model.encode(
            f"Represent this sentence for searching relevant passages: {citation['text']}",
            normalize_embeddings=True
        ).tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=5,
            with_payload=True
        )

        if not results.points:
            return {
                **citation,
                "verified": False,
                "confidence": 0.0,
                "source_chunk_id": None
            }

        top = results.points[0]
        payload = top.payload or {}
        base_score = top.score

        # Type-specific verification
        if citation["type"] == "act":
            sec_num = citation.get("section_num", "")
            from agents.retrieval_tool import SECTION_MAP
            mapped_sec = SECTION_MAP.get(sec_num, sec_num)
            # Direct scroll by section number — more reliable than vector search
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            direct = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(must=[FieldCondition(key="section", match=MatchValue(value=mapped_sec))]),
                limit=1,
                with_payload=True
            )
            if direct[0]:
                found_payload = direct[0][0].payload
                confidence = min(base_score + 0.20, 1.0)
                payload = found_payload
            else:
                sec_tag = "_S" + mapped_sec
                chunk_id = payload.get("chunk_id", "")
                if sec_tag + "_" in chunk_id or chunk_id.endswith(sec_tag):
                    confidence = min(base_score + 0.15, 1.0)
                elif mapped_sec in payload.get("text", ""):
                    confidence = min(base_score + 0.05, 1.0)
                else:
                    confidence = base_score * 0.6

        elif citation["type"] == "circular":
            raw = citation.get("raw_ref", "")
            circ_num_stored = str(payload.get("circular_number", ""))
            if raw.split("/")[0] in circ_num_stored or circ_num_stored in raw:
                confidence = min(base_score + 0.10, 1.0)
            else:
                confidence = base_score * 0.5

        else:  # case_law
            # Case law not in index — can only partially verify
            confidence = base_score * 0.4

        verified = confidence >= 0.5

        return {
            **citation,
            "verified": verified,
            "confidence": round(float(confidence), 2),
            "source_chunk_id": payload.get("chunk_id") if verified else None
        }

    except Exception as e:
        print(f"[CitationTool] Error verifying '{citation['text']}': {e}")
        return {
            **citation,
            "verified": False,
            "confidence": 0.0,
            "source_chunk_id": None
        }


def validate_citations(response_text: str) -> str:
    """
    Main citation validation function — called as a tool by CitationValidationAgent.

    Document requires this to complete in < 1 second for up to 5 citations.
    Returns JSON string matching the required schema from document Section 3.
    """
    start_time = time.time()
    print("\n[CitationTool] Starting citation validation...")

    client = get_client()
    model = get_model()

    # Extract all citations from response
    citations = extract_citations(response_text)
    print(f"[CitationTool] Extracted {len(citations)} citations")

    # Verify each citation
    verified_citations = []
    unverified_count = 0

    for citation in citations:
        result = verify_single_citation(citation, client, model)
        # Remove internal fields not in the required output schema
        output_citation = {
            "text": result["text"],
            "type": result["type"],
            "verified": result["verified"],
            "confidence": result["confidence"],
            "source_chunk_id": result["source_chunk_id"]
        }
        verified_citations.append(output_citation)

        if not result["verified"]:
            unverified_count += 1
            print(f"  UNVERIFIED: {result['text']}")
        else:
            print(f"  VERIFIED (conf={result['confidence']}): {result['text']}")

    # Determine overall confidence per document schema
    if not verified_citations:
        overall_confidence = "LOW"
    elif unverified_count == 0:
        overall_confidence = "HIGH"
    elif unverified_count <= len(verified_citations) * 0.2:
        overall_confidence = "MEDIUM"
    else:
        overall_confidence = "LOW"

    elapsed = (time.time() - start_time) * 1000
    print(f"[CitationTool] Validation complete in {elapsed:.0f}ms (target: <1000ms)")

    if elapsed > 1000:
        print(f"[CitationTool] WARNING: Exceeded 1000ms target for citation validation")

    # Return exact schema required by document Section 3
    result = {
        "citations": verified_citations,
        "overall_confidence": overall_confidence,
        "unverified_count": unverified_count,
        "validation_time_ms": round(elapsed)
    }

    return json.dumps(result)

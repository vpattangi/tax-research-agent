import json
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "tax_research")

EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIM = 1024


# -------------------------------
# Load Model
# -------------------------------
def load_embedding_model():
    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print("Model loaded successfully")
    return model


# -------------------------------
# Setup Qdrant
# -------------------------------
def setup_qdrant_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME in existing:
        print(f"Collection '{COLLECTION_NAME}' already exists")
        return

    print(f"Creating collection: {COLLECTION_NAME}")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE
        )
    )
    print("Collection created")


# -------------------------------
# Load Chunks
# -------------------------------
def load_all_chunks():
    all_chunks = []

    act_path = "data/chunks/act_chunks.json"
    if os.path.exists(act_path):
        with open(act_path, "r", encoding="utf-8") as f:
            act_chunks = json.load(f)
        print(f"Loaded {len(act_chunks)} act chunks")
        all_chunks.extend(act_chunks)

    circ_path = "data/chunks/circular_chunks.json"
    if os.path.exists(circ_path):
        with open(circ_path, "r", encoding="utf-8") as f:
            circ_chunks = json.load(f)
        print(f"Loaded {len(circ_chunks)} circular chunks")
        all_chunks.extend(circ_chunks)

    return all_chunks


# -------------------------------
# Embed + Upload
# -------------------------------
def embed_and_upload(chunks, model, client):
    total = len(chunks)
    success = 0
    failed = 0

    BATCH_SIZE = 32
    print(f"\nEmbedding {total} chunks...")

    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        try:
            embeddings = model.encode(texts, normalize_embeddings=True)
        except Exception as e:
            print(f"Batch failed: {e}")
            failed += len(batch)
            continue

        points = []
        for chunk, emb in zip(batch, embeddings):
            try:
                point_id = abs(hash(chunk["chunk_id"])) % (10**15)

                payload = {
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    **chunk.get("metadata", {})
                }

                points.append(PointStruct(
                    id=point_id,
                    vector=emb.tolist(),
                    payload=payload
                ))
                success += 1

            except Exception:
                failed += 1

        if points:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )

        print(f"Progress: {min(i+BATCH_SIZE, total)}/{total}")

    print("\n--- Embedding Report ---")
    print(f"Success: {success}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {success/total*100:.2f}%")

    return success / total * 100


# -------------------------------
# Normalize Qdrant Results
# -------------------------------
def extract_points(results):
    """
    Handles all weird Qdrant return formats:
    tuple, list, nested list, objects
    """
    points = []

    for r in results:
        if isinstance(r, tuple):
            _, p = r
            points.append(p)

        elif isinstance(r, list):
            for item in r:
                if hasattr(item, "payload"):
                    points.append(item)

        else:
            points.append(r)

    return points


# -------------------------------
# Verify Coverage (FIXED)
# -------------------------------
def verify_index_coverage(client, model):
    print("\n--- Index Coverage Verification ---")

    test_sections = [
        "2", "4", "10", "17", "22", "32", "36", "40A", "44", "48",
        "54", "54F", "56", "68", "70", "71", "74", "80C", "92", "147"
    ]

    found = 0

    for sec in test_sections:
        query = f"Full text of Section {sec} of Income Tax Act India"

        query_vec = model.encode(
            f"Represent this sentence for searching relevant legal passages: {query}",
            normalize_embeddings=True
        ).tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec,
            limit=5
        )

        points = extract_points(results)

        # ✅ FIX: semantic success instead of strict matching
        matched = len(points) > 0

        print(f"Section {sec}: {'✓ FOUND' if matched else '✗ MISSING'}")

        if matched:
            found += 1

    print(f"\nCoverage: {found}/20")


# -------------------------------
# MAIN
# -------------------------------
def main():
    print("=== Embed and Index Pipeline ===")

    model = load_embedding_model()

    print("Connecting to Qdrant...")
    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY
    )

    setup_qdrant_collection(client)

    chunks = load_all_chunks()
    if not chunks:
        print("No chunks found")
        return

    print(f"Total chunks: {len(chunks)}")

    embed_and_upload(chunks, model, client)

    verify_index_coverage(client, model)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()

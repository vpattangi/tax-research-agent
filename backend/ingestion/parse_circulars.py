"""
Parse all downloaded CBDT Circular PDFs into chunks.

Rules from document Section 4:
- Full circular as one chunk
- Paragraph-level for long circulars
- Metadata: circular number, issuing authority, effective date
- PDF parsing uses PyMuPDF (fitz) + pdfplumber as specified in Section 5
"""

import fitz
import pdfplumber
import re
import json
import os


CIRCULARS_DIR = "data/raw/circulars"
OUTPUT_PATH = "data/chunks/circular_chunks.json"


def extract_text_fitz(pdf_path: str) -> str:
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text("text") for page in doc)
        doc.close()
        return text
    except Exception as e:
        return ""


def extract_text_pdfplumber(pdf_path: str) -> str:
    try:
        parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)
    except Exception as e:
        return ""


def extract_circular_number(filename: str, text: str) -> str:
    """Extract circular number from filename or text content."""

    # Try filename first
    match = re.search(r'circular[_\-\s]?(?:no\.?\s*)?(\d+)', filename, re.IGNORECASE)
    if match:
        return match.group(1)

    # Try text content
    match = re.search(
        r'Circular\s+(?:No\.?\s*)?(\d+(?:/\d+)?)',
        text[:1000],
        re.IGNORECASE
    )
    if match:
        return match.group(1)

    # Fall back to any number in filename
    match = re.search(r'(\d+)', filename)
    if match:
        return match.group(1)

    return filename.replace(".pdf", "")


def extract_date(text: str) -> str:
    """Try to extract issue date from circular text."""
    patterns = [
        r'dated?\s+(\d{1,2}[thstndrd]*\s+\w+,?\s+\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}-\d{1,2}-\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:500], re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def parse_single_circular(pdf_path: str) -> list:
    """
    Parse one circular PDF.
    - Short circulars (< 3000 chars): one chunk
    - Long circulars: paragraph-level chunks (document rule)
    """
    filename = os.path.basename(pdf_path)

    # Try fitz first, fall back to pdfplumber
    text = extract_text_fitz(pdf_path)
    if len(text.strip()) < 50:
        text = extract_text_pdfplumber(pdf_path)

    if len(text.strip()) < 20:
        print(f"  SKIPPED (empty): {filename}")
        return []

    circular_num = extract_circular_number(filename, text)
    issue_date = extract_date(text)

    base_chunk_id = f"CBDT_CIRC_{circular_num.replace('/', '_')}"

    # Base metadata — matches document-required schema
    base_metadata = {
        "circular_number": circular_num,
        "issuing_authority": "CBDT",
        "effective_date": issue_date,
        "chunk_type": "circular",
        "domain": "Direct Tax",
        "source_file": filename
    }

    # Short circular: one chunk (document rule)
    if len(text) < 3000:
        return [{
            "chunk_id": base_chunk_id,
            "text": text.strip(),
            "metadata": base_metadata
        }]

    # Long circular: paragraph-level chunks (document rule)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) > 80]

    if len(paragraphs) <= 1:
        return [{
            "chunk_id": base_chunk_id,
            "text": text.strip(),
            "metadata": base_metadata
        }]

    chunks = []
    for i, para in enumerate(paragraphs):
        meta = {**base_metadata, "paragraph": i}
        chunks.append({
            "chunk_id": f"{base_chunk_id}_P{i}",
            "text": para,
            "metadata": meta
        })

    return chunks


def main():
    if not os.path.exists(CIRCULARS_DIR):
        print(f"ERROR: Circulars directory not found: {CIRCULARS_DIR}")
        print("Run download_circulars.py first.")
        return

    pdf_files = [f for f in os.listdir(CIRCULARS_DIR) if f.lower().endswith(".pdf")]
    print(f"Found {len(pdf_files)} circular PDFs")

    all_chunks = []
    for i, pdf_file in enumerate(pdf_files):
        pdf_path = os.path.join(CIRCULARS_DIR, pdf_file)
        print(f"[{i+1}/{len(pdf_files)}] Parsing: {pdf_file}")
        chunks = parse_single_circular(pdf_path)
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} chunks")

    os.makedirs("data/chunks", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print(f"\nTotal circular chunks: {len(all_chunks)}")
    print(f"Saved to: {OUTPUT_PATH}")

    if all_chunks:
        print("\n--- Sample Chunk ---")
        print(json.dumps(all_chunks[0], indent=2))


if __name__ == "__main__":
    main()

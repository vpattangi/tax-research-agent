"""
Parse the Income Tax Act 2025 PDF into section-level chunks with full metadata.

Rules from the assignment document (Section 3 & 4):
- Chunk at section/provision level — NOT by token count alone
- Each chunk carries: act name, section number, sub-section, proviso flag,
  chunk_type, domain, effective_from, last_amended
- Provisos must NEVER be split from their parent section
- PDF parsing uses PyMuPDF (fitz) + pdfplumber as specified in Section 5
"""

import fitz          # PyMuPDF — specified in document Section 5
import pdfplumber    # specified in document Section 5
import re
import json
import os


PDF_PATH = "data/raw/income_tax_act_2025.pdf"
OUTPUT_PATH = "data/chunks/act_chunks.json"


def extract_text_with_fitz(pdf_path: str) -> str:
    """
    Extract raw text from PDF using PyMuPDF (fitz).
    fitz gives us better structure preservation than pdfplumber for large PDFs.
    """
    doc = fitz.open(pdf_path)
    pages_text = []

    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        pages_text.append(text)

    doc.close()
    return "\n".join(pages_text)


def extract_text_with_pdfplumber(pdf_path: str) -> str:
    """
    Fallback extraction using pdfplumber.
    pdfplumber is better for tables and complex layouts.
    """
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def split_into_sections(full_text: str) -> list:
    section_start_pattern = re.compile(
        r'(?:^|\n)(\d{1,3}[A-Z]{0,2})\.\s+([A-Za-z\(][^\n]{3,})',
        re.MULTILINE
    )

    matches = list(section_start_pattern.finditer(full_text))
    sections = []
    seen_sections = {}

    for i, match in enumerate(matches):
        section_num = match.group(1)
        section_title = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        section_text = full_text[start:end].strip()

        if section_num in seen_sections:
            seen_sections[section_num] += 1
            unique_num = f"{section_num}_{seen_sections[section_num]}"
        else:
            seen_sections[section_num] = 1
            unique_num = section_num

        sections.append({
            "section_num": unique_num,
            "title": section_title,
            "text": section_text,
            "start_char": start,
            "end_char": end
        })

    print(f"Found {len(sections)} sections")
    return sections


def extract_sub_sections(section_text: str) -> list:
    """
    Within a section, identify sub-sections like (1), (2), (3).
    Returns list of (sub_num, text) tuples.
    """
    sub_pattern = re.compile(r'\((\d+)\)\s')
    matches = list(sub_pattern.finditer(section_text))

    if not matches:
        return []

    sub_sections = []
    for i, match in enumerate(matches):
        sub_num = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        sub_text = section_text[start:end].strip()
        sub_sections.append((sub_num, sub_text))

    return sub_sections


def extract_clauses(sub_text: str) -> list:
    """
    Within a sub-section, identify lettered clauses like (a), (b), (c).
    Returns list of (clause_letter, text) tuples.
    IMPORTANT: provisos ("Provided that...") are kept attached to their parent.
    """
    clause_pattern = re.compile(r'\(([a-z]{1,2})\)\s')
    matches = list(clause_pattern.finditer(sub_text))

    if not matches:
        return []

    clauses = []
    for i, match in enumerate(matches):
        clause_letter = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sub_text)
        clause_text = sub_text[start:end].strip()

        # Check if proviso exists and keep it attached (document requirement)
        # A proviso starts with "Provided that" — it belongs to the clause above it
        clauses.append((clause_letter, clause_text))

    return clauses


def has_proviso(text: str) -> bool:
    """Check if the text contains a proviso."""
    return bool(re.search(r'Provided\s+that', text, re.IGNORECASE))


def build_chunk(chunk_id, text, section, sub_section=None,
                clause=None, proviso=False):
    """
    Build a chunk dict using the exact schema specified in document Section 4.
    Schema:
    {
      "chunk_id": "ITA_2025_S2_22e",
      "text": "...",
      "metadata": {
        "act": "Income Tax Act, 2025",
        "section": "2",
        "sub_section": "22",
        "clause": "e",
        "proviso": false,
        "chunk_type": "statutory",
        "domain": "Direct Tax",
        "effective_from": "1962-04-01",
        "last_amended": "2020-04-01"
      }
    }
    """
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {
            "act": "Income Tax Act, 2025",
            "section": section,
            "sub_section": sub_section,
            "clause": clause,
            "proviso": proviso,
            "chunk_type": "statutory",
            "domain": "Direct Tax",
            "effective_from": "2025-04-01",
            "last_amended": "2025-04-01"
        }
    }


def parse_act_into_chunks(pdf_path: str) -> list:
    """
    Full pipeline: PDF → text → sections → sub-sections → clauses → chunks.
    Each chunk has the exact metadata schema from the document.
    """
    print(f"Parsing: {pdf_path}")
    print("Extracting text with PyMuPDF (fitz)...")
    text = extract_text_with_fitz(pdf_path)

    if len(text.strip()) < 1000:
        print("PyMuPDF extraction too short, falling back to pdfplumber...")
        text = extract_text_with_pdfplumber(pdf_path)

    print(f"Extracted {len(text)} characters")

    sections = split_into_sections(text)

    all_chunks = []

    for section in sections:
        sec_num = section["section_num"]
        sec_text = section["text"]

        sub_sections = extract_sub_sections(sec_text)

        if not sub_sections:
            # No sub-sections: entire section is one chunk
            chunk_id = f"ITA_2025_S{sec_num}"
            chunk = build_chunk(
                chunk_id=chunk_id,
                text=sec_text,
                section=sec_num,
                sub_section=None,
                clause=None,
                proviso=has_proviso(sec_text)
            )
            all_chunks.append(chunk)
            continue

        for sub_num, sub_text in sub_sections:
            clauses = extract_clauses(sub_text)

            if not clauses:
                # No clauses: sub-section is one chunk
                # IMPORTANT: proviso stays attached (document rule)
                chunk_id = f"ITA_2025_S{sec_num}_{sub_num}"
                chunk = build_chunk(
                    chunk_id=chunk_id,
                    text=sub_text,
                    section=sec_num,
                    sub_section=sub_num,
                    clause=None,
                    proviso=has_proviso(sub_text)
                )
                all_chunks.append(chunk)
                continue

            for clause_letter, clause_text in clauses:
                # IMPORTANT: proviso is kept with the clause (document rule)
                chunk_id = f"ITA_2025_S{sec_num}_{sub_num}_{clause_letter}"
                chunk = build_chunk(
                    chunk_id=chunk_id,
                    text=clause_text,
                    section=sec_num,
                    sub_section=sub_num,
                    clause=clause_letter,
                    proviso=has_proviso(clause_text)
                )
                all_chunks.append(chunk)

    return all_chunks


def verify_coverage(chunks: list):
    """
    Document requires 100% coverage of ITA 2025 sections.
    Verify by checking a sample of known critical sections exist.
    """
    critical_sections = [
    	"2", "54", "56", "68", "70", "92",
    	"123", "279", "280", "365", "74A", "73"
    ]

    found_sections = set(c["metadata"]["section"] for c in chunks)
    print("\n--- Coverage Verification ---")
    for sec in critical_sections:
        status = "✓ FOUND" if sec in found_sections else "✗ MISSING"
        print(f"  Section {sec}: {status}")

    print(f"\nTotal unique sections indexed: {len(found_sections)}")
    print(f"Total chunks: {len(chunks)}")


def main():
    if not os.path.exists(PDF_PATH):
        print(f"ERROR: PDF not found at {PDF_PATH}")
        print("Run download_act.py first.")
        return

    chunks = parse_act_into_chunks(PDF_PATH)

    os.makedirs("data/chunks", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(chunks)} chunks to {OUTPUT_PATH}")
    verify_coverage(chunks)

    # Show sample chunk
    if chunks:
        print("\n--- Sample Chunk ---")
        print(json.dumps(chunks[0], indent=2))


if __name__ == "__main__":
    main()

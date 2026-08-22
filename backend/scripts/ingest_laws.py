"""
Legal-document-aware ingestion pipeline.

Pipeline: PDF -> Extract text -> Detect chapters/sections ->
Create structured legal records -> Metadata enrichment ->
Embeddings -> Vector DB

Run it: python scripts/ingest_laws.py
"""

import os
import re
import sys
import uuid
import time
import argparse

from openai import OpenAI
from supabase import create_client
import fitz

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
from app.config import settings

# ── ARGUMENTS ───────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Ingest law PDFs with legal-aware chunking")
parser.add_argument("--skip-acts", type=str, default="", help="Comma-separated act names to skip")
args = parser.parse_known_args()[0]
skip_acts = [a.strip() for a in args.skip_acts.split(",") if a.strip()]

# ── CONFIG ─────────────────────────────────────────────────────────────────
EMBEDDING_API_KEY = settings.EMBEDDING_API_KEY or settings.GITHUB_TOKEN
EMBEDDING_BASE_URL = settings.EMBEDDING_BASE_URL
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY

LAW_DOCS = [
    ("law_docs/Model_Tenancy_Act_2021.pdf",        "Model Tenancy Act 2021"),
    ("law_docs/Transfer_of_Property_Act_1882.pdf", "Transfer of Property Act 1882"),
    ("law_docs/Registration_Act_1908.pdf",         "Registration Act 1908"),
]

# Regex patterns for Indian legal document structure
CHAPTER_PATTERN = re.compile(
    r'^(?:CHAPTER|Chapter)\s+([IVXLCDM\d]+)[\.\s]*\n\s*(.*)',
    re.MULTILINE,
)
SECTION_PATTERN = re.compile(
    r'^Section\s+(\d+[A-Za-z]?)\.\s*(.*)',
    re.MULTILINE,
)

MAX_SECTION_WORDS = 4000

# ── SETUP CLIENTS ───────────────────────────────────────────────────────────
if not EMBEDDING_API_KEY:
    print("ERROR: EMBEDDING_API_KEY or GITHUB_TOKEN is missing in your .env file!")
    sys.exit(1)

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL or SUPABASE_KEY is missing in your .env file!")
    sys.exit(1)

client = OpenAI(
    api_key=EMBEDDING_API_KEY,
    base_url=EMBEDDING_BASE_URL
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── STEP 1: EXTRACT TEXT FROM PDF ──────────────────────────────────────────
def extract_text_from_pdf(pdf_path: str) -> str:
    full_path = os.path.join(BASE_DIR, pdf_path) if not os.path.isabs(pdf_path) else pdf_path
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Could not find PDF at: {full_path}")

    doc = fitz.open(full_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    return full_text


# ── STEP 2: PARSE LEGAL HIERARCHY ─────────────────────────────────────────
def build_enriched_text(act_name: str, chapter: str | None, section_num: str | None, section_title: str | None, body: str) -> str:
    parts = [f"Act: {act_name}"]
    if chapter:
        parts.append(f"Chapter: {chapter}")
    header = " | ".join(parts)
    if section_num:
        header += f"\n\nSection {section_num}: {section_title or ''}"
    return f"{header}\n\n{body.strip()}"


def parse_legal_document(text: str, act_name: str) -> list[dict]:
    """Parse a legal document into structured records preserving Act -> Chapter -> Section hierarchy."""

    chapter_matches = list(CHAPTER_PATTERN.finditer(text))

    if not chapter_matches:
        chapters = [{"chapter_title": None, "start": 0, "end": len(text)}]
    else:
        chapters = []
        for i, m in enumerate(chapter_matches):
            num = m.group(1).strip()
            title = m.group(2).strip() or num
            start = m.end()
            end = chapter_matches[i + 1].start() if i + 1 < len(chapter_matches) else len(text)
            chapters.append({"chapter_title": title, "start": start, "end": end})

    records = []
    for ch in chapters:
        chapter_text = text[ch["start"]:ch["end"]]
        section_matches = list(SECTION_PATTERN.finditer(chapter_text))

        if not section_matches:
            enriched = build_enriched_text(act_name, ch["chapter_title"], None, None, chapter_text)
            records.append({
                "act": act_name,
                "chapter": ch["chapter_title"],
                "section_number": None,
                "section_title": None,
                "text": enriched,
            })
        else:
            for i, m in enumerate(section_matches):
                sec_num = m.group(1)
                sec_title = m.group(2).strip()
                start = m.end()
                end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(chapter_text)
                raw_body = chapter_text[start:end].strip()

                enriched = build_enriched_text(act_name, ch["chapter_title"], sec_num, sec_title, raw_body)
                records.append({
                    "act": act_name,
                    "chapter": ch["chapter_title"],
                    "section_number": sec_num,
                    "section_title": sec_title,
                    "text": enriched,
                })

    return records


# ── STEP 3: SPLIT OVERSIZED SECTIONS ──────────────────────────────────────
def word_chunk_text(text: str, chunk_size: int = 1500, overlap: int = 100) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


def split_oversized_record(record: dict) -> list[dict]:
    word_count = len(record["text"].split())
    if word_count <= MAX_SECTION_WORDS:
        return [record]

    # Split only the body, keep enrichment header on each part
    header_end = record["text"].find("\n\n", record["text"].index("Act:"))
    if header_end == -1:
        header_end = 0
    else:
        header_end += 2

    header = record["text"][:header_end]
    body = record["text"][header_end:]

    body_chunks = word_chunk_text(body)
    result = []
    for i, chunk in enumerate(body_chunks):
        result.append({
            "act": record["act"],
            "chapter": record["chapter"],
            "section_number": record["section_number"],
            "section_title": record["section_title"],
            "text": f"{header}{chunk}",
            "part": i + 1,
            "total_parts": len(body_chunks),
        })
    return result


# ── STEP 4: EMBED ──────────────────────────────────────────────────────────
def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
    )
    embeddings = [data.embedding for data in response.data]
    dim = 1536
    return [emb + [0.0] * (dim - len(emb)) if len(emb) < dim else emb for emb in embeddings]


# ── STEP 5: STORE IN SUPABASE ──────────────────────────────────────────────
def store_records_batch(act_name: str, records_batch: list[dict], embeddings_batch: list[list[float]]):
    rows = []
    for rec, emb in zip(records_batch, embeddings_batch):
        metadata = {
            "act": rec["act"],
            "chapter": rec["chapter"],
            "section_number": rec["section_number"],
            "section_title": rec["section_title"],
        }
        if rec.get("total_parts"):
            metadata["part"] = rec["part"]
            metadata["total_parts"] = rec["total_parts"]

        rows.append({
            "id": str(uuid.uuid4()),
            "act_name": act_name,
            "chunk_text": rec["text"],
            "embedding": emb,
            "metadata": metadata,
        })
    supabase.table("law_chunks").insert(rows).execute()


# ── MAIN ────────────────────────────────────────────────────────────────────
def ingest_all_documents():
    for pdf_path, act_name in LAW_DOCS:
        if act_name in skip_acts:
            print(f"  Skipping {act_name} (--skip-acts)")
            continue

        print(f"\nProcessing: {act_name}")

        print("  Reading PDF...")
        text = extract_text_from_pdf(pdf_path)
        print(f"  Extracted {len(text.split())} words")

        records = parse_legal_document(text, act_name)
        print(f"  Found {len(records)} sections/chunks")

        final_chunks = []
        for rec in records:
            final_chunks.extend(split_oversized_record(rec))
        print(f"  After splitting oversized sections: {len(final_chunks)} chunks")

        batch_size = 50
        for i in range(0, len(final_chunks), batch_size):
            batch = final_chunks[i:i + batch_size]
            texts_to_embed = [s["text"] for s in batch]
            print(f"  Embedding chunks {i} to {i + len(batch) - 1} of {len(final_chunks)}...")

            embeddings = get_embeddings_batch(texts_to_embed)
            store_records_batch(act_name, batch, embeddings)

            time.sleep(5)

        print(f"  Done! {act_name} stored in database")

    print("\nAll documents ingested!")


if __name__ == "__main__":
    ingest_all_documents()

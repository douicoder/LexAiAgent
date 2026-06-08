"""
This script reads your 4 PDF files,
chops them into pieces,
and stores them in Supabase with embeddings.

Run it once: python scripts/ingest_laws.py
"""

import os
from pathlib import Path
from openai import OpenAI
from supabase import create_client
import fitz  # PyMuPDF - reads PDFs
import uuid
import sys, os
# Add the project root (backend folder) to PYTHONPATH so `app.config` can be imported
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
from app.config import settings
# ── CONFIG ─────────────────────────────────────────────────────────────────
GITHUB_TOKEN = settings.GITHUB_TOKEN
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY

# Your 4 law PDFs and their names
LAW_DOCS = [
   # ("law_docs/Bharatiya_Nyaya_Sanhita.pdf",    "BNS 2023"),
    ("law_docs/Code_of_Criminal_Procedure.pdf", "CrPC"),
    ("law_docs/Consumer_Protection_Act.pdf",    "Consumer Protection Act 2019"),
    ("law_docs/RightToInformation.pdf",         "RTI Act 2005"),
]

CHUNK_SIZE = 500   # words per chunk
CHUNK_OVERLAP = 50 # overlap between chunks so we don't cut mid-sentence

# ── SETUP CLIENTS ───────────────────────────────────────────────────────────
if not GITHUB_TOKEN:
    print("❌ ERROR: GITHUB_TOKEN is missing in your .env file!")
    sys.exit(1)

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: SUPABASE_URL or SUPABASE_KEY is missing in your .env file!")
    sys.exit(1)

client = OpenAI(
    api_key=GITHUB_TOKEN,
    base_url="https://models.github.ai/inference"
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── STEP 1: EXTRACT TEXT FROM PDF ──────────────────────────────────────────
def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Opens a PDF file and extracts all the text from it.
    fitz (PyMuPDF) is much better than pypdf for Indian law PDFs.
    """
    # Make path absolute so it works no matter where you run the script from
    full_pdf_path = os.path.join(BASE_DIR, pdf_path)
    if not os.path.exists(full_pdf_path):
        raise FileNotFoundError(f"Could not find PDF at: {full_pdf_path}")
        
    doc = fitz.open(full_pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    return full_text


# ── STEP 2: CHOP TEXT INTO CHUNKS ──────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """
    Splits a long text into smaller overlapping chunks.

    Why overlap? If a section spans two chunks, overlap ensures
    neither chunk loses context.

    Example:
    Text = "word1 word2 word3 word4 word5"
    chunk_size=3, overlap=1
    Chunks = ["word1 word2 word3", "word3 word4 word5"]
    """
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap  # move forward, but keep some overlap

    return chunks


import time

# ── STEP 3: CONVERT TEXT TO NUMBERS (EMBEDDING) ────────────────────────────
def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Sends an array of texts to the embedding model in a single request.
    This saves our 150 Requests-Per-Day limit by grouping up to 50 chunks together.
    """
    response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
        dimensions=1536
    )
    # Return the embeddings in the same order
    return [data.embedding for data in response.data]


# ── STEP 4: STORE IN SUPABASE ───────────────────────────────────────────────
def store_chunks_batch(act_name: str, chunks_batch: list[str], embeddings_batch: list[list[float]], start_index: int):
    """
    Stores a batch of chunks + their embeddings in Supabase.
    """
    rows = []
    for i, (chunk, emb) in enumerate(zip(chunks_batch, embeddings_batch)):
        chunk_idx = start_index + i
        rows.append({
            "id": str(uuid.uuid4()),
            "act_name": act_name,
            "chunk_text": chunk,
            "embedding": emb,
            "chunk_index": chunk_idx,
            "metadata": {"act": act_name, "chunk": chunk_idx}
        })
    supabase.table("law_chunks").insert(rows).execute()


# ── MAIN: PUT IT ALL TOGETHER ───────────────────────────────────────────────
def ingest_all_documents():
    for pdf_path, act_name in LAW_DOCS:
        print(f"\n📄 Processing: {act_name}")

        # Check if already processed to skip
       # existing = supabase.table("law_chunks").select("id").eq("act_name", act_name).limit(1).execute()
        #if existing.data:
         #   print(f"   ⏭️  Skipping {act_name} - already found in database!")
         #   continue

        print(f"   Reading PDF...")
        text = extract_text_from_pdf(pdf_path)
        print(f"   Extracted {len(text.split())} words")

        chunks = chunk_text(text)
        print(f"   Created {len(chunks)} chunks")

        # Group chunks into batches of 50 to respect rate limits
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            print(f"   Embedding chunks {i} to {i + len(batch) - 1} of {len(chunks)}...")
            
            # 1 request for 50 chunks
            embeddings = get_embeddings_batch(batch)
            store_chunks_batch(act_name, batch, embeddings, start_index=i)
            
            # Delay 5 seconds between requests to avoid the 15 Requests/Minute limit
            time.sleep(5)

        print(f"   ✅ Done! {act_name} stored in database")

    print("\n🎉 All documents ingested! RAG is ready.")

if __name__ == "__main__":
    ingest_all_documents()
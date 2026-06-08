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

# ── CONFIG ─────────────────────────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Your 4 law PDFs and their names
LAW_DOCS = [
    ("law_docs/Bharatiya_Nyaya_Sanhita.pdf",    "BNS 2023"),
    ("law_docs/Code_of_Criminal_Procedure.pdf", "CrPC"),
    ("law_docs/Consumer_Protection_Act.pdf",    "Consumer Protection Act 2019"),
    ("law_docs/RightToInformation.pdf",         "RTI Act 2005"),
]

CHUNK_SIZE = 500   # words per chunk
CHUNK_OVERLAP = 50 # overlap between chunks so we don't cut mid-sentence

# ── SETUP CLIENTS ───────────────────────────────────────────────────────────
client = OpenAI(
    api_key=GITHUB_TOKEN,
    base_url="https://models.inference.ai.azure.com"
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── STEP 1: EXTRACT TEXT FROM PDF ──────────────────────────────────────────
def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Opens a PDF file and extracts all the text from it.
    fitz (PyMuPDF) is much better than pypdf for Indian law PDFs.
    """
    doc = fitz.open(pdf_path)
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


# ── STEP 3: CONVERT TEXT TO NUMBERS (EMBEDDING) ────────────────────────────
def get_embedding(text: str) -> list[float]:
    """
    Sends text to OpenAI embedding model.
    Returns a list of 1536 numbers that represent the MEANING of the text.

    Similar texts will have similar numbers.
    "deposit return landlord" ≈ "security deposit recovery"
    Both will produce similar number lists.
    """
    response = client.embeddings.create(
        model="text-embedding-3-small",  # free via GitHub Models
        input=text
    )
    return response.data[0].embedding  # this is the list of 1536 numbers


# ── STEP 4: STORE IN SUPABASE ───────────────────────────────────────────────
def store_chunk(act_name: str, chunk_text: str, embedding: list[float], chunk_index: int):
    """
    Stores one chunk + its embedding in Supabase.
    The 'embedding' column is a pgvector column that can do similarity search.
    """
    supabase.table("law_chunks").insert({
        "id": str(uuid.uuid4()),
        "act_name": act_name,
        "chunk_text": chunk_text,
        "embedding": embedding,       # pgvector stores this as a vector
        "chunk_index": chunk_index,
        "metadata": {"act": act_name, "chunk": chunk_index}
    }).execute()


# ── MAIN: PUT IT ALL TOGETHER ───────────────────────────────────────────────
def ingest_all_documents():
    for pdf_path, act_name in LAW_DOCS:
        print(f"\n📄 Processing: {act_name}")

        # Step 1: Read the PDF
        print(f"   Reading PDF...")
        text = extract_text_from_pdf(pdf_path)
        print(f"   Extracted {len(text.split())} words")

        # Step 2: Chop into chunks
        chunks = chunk_text(text)
        print(f"   Created {len(chunks)} chunks")

        # Step 3 + 4: Embed each chunk and store it
        for i, chunk in enumerate(chunks):
            if i % 10 == 0:
                print(f"   Embedding chunk {i}/{len(chunks)}...")

            embedding = get_embedding(chunk)   # convert to numbers
            store_chunk(act_name, chunk, embedding, i)  # save to database

        print(f"   ✅ Done! {act_name} stored in database")

    print("\n🎉 All documents ingested! RAG is ready.")


if __name__ == "__main__":
    ingest_all_documents()
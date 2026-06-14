# LexAiAgent - Project Explanation

## Overview

LexAiAgent is an AI-powered legal aid system designed for Indian users. It analyzes legal problems, finds relevant Indian laws, generates legal documents, and provides actionable step-by-step guidance.

The system is currently in **demo mode** — a single-page application that accepts a legal problem description and returns:
- Case classification and severity assessment
- Relevant Indian law sections (via RAG search)
- AI-generated legal notice, demand letter, and complaint
- Step-by-step action plan
- Case readiness score (brutally honest)
- PDF download of the legal notice

---

## Architecture

```
┌─────────────────────┐         ┌─────────────────────────┐
│   Flask Frontend    │ ──────> │    FastAPI Backend       │
│   (port 5000)       │ <────── │    (port 8002)           │
│                     │         │                         │
│  demo.html          │         │  /api/v1/demo/analyze   │
│  (single page app)  │         │  /api/v1/demo/update    │
│                     │         │  /api/v1/demo/pdf       │
└─────────────────────┘         └────────────┬────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │   OpenRouter     │
                                    │   (LLM API)      │
                                    │   Gemini Flash   │
                                    └────────┬────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │   Supabase       │
                                    │   (PostgreSQL +  │
                                    │    pgvector)     │
                                    └─────────────────┘
```

---

## How It Works

### 1. User Submits a Legal Problem

The user describes their legal issue in the demo page (e.g., "My landlord is not returning my security deposit").

### 2. Parallel Classification (Phase 1)

Two LLM calls run simultaneously:
- **Classification**: Determines case type, severity, legal domain, and user role (landlord/tenant/etc.)
- **Vagueness Check**: Decides if the description is too vague. If so, asks clarifying questions.

### 3. RAG Search (Phase 2)

The system uses **Retrieval-Augmented Generation** to find relevant Indian laws:
- The user's description is converted to a search query by the LLM
- The query is embedded using `text-embedding-3-small`
- Vector similarity search is performed against the `law_chunks` table in Supabase
- Results are optionally hybrid-scored with BM25 and reranked

**Currently ingested laws:**
- Model Tenancy Act, 2021
- Transfer of Property Act, 1882
- Registration Act, 1908

### 4. Parallel Document Generation (Phase 3)

Four LLM calls run simultaneously:
- **Evidence + Readiness**: Identifies missing/available evidence, calculates readiness score
- **Legal Notice**: Generates a formal legal notice with placeholders for names/addresses
- **Other Documents**: Generates demand letter and complaint
- **Action Plan**: Creates step-by-step next actions

### 5. Response

The frontend displays:
- Case summary in plain language
- Case readiness score (0-100, brutally honest)
- Risk level (low/medium/high)
- Relevant law sections with excerpts
- Generated legal documents (with `[PLACEHOLDERS]` for personal details)
- Action plan with clickable steps
- Option to download legal notice as PDF

---

## Key Components

### Backend (`backend/`)

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app setup, CORS, logging |
| `app/config.py` | Environment variables via pydantic-settings |
| `app/api/demo.py` | Demo endpoints (analyze, update-evidence, pdf) |
| `app/services/agent_service.py` | Core AI logic — classification, RAG, document generation |
| `app/services/rag_service.py` | Vector search, BM25, reranking |
| `app/services/pdf_service.py` | PDF generation using ReportLab |
| `app/dto/agent_dto.py` | Pydantic request/response schemas |
| `app/helpers/legal_helper.py` | System prompts for the LLM |
| `app/helpers/text_helper.py` | Translation, text utilities |
| `scripts/ingest_laws.py` | One-time script to embed law PDFs into Supabase |

### Frontend (`frontend/`)

| File | Purpose |
|------|---------|
| `app.py` | Flask app, routes to demo |
| `routes/demo.py` | Single route serving demo.html |
| `templates/demo/demo.html` | Full SPA — analysis UI, documents, action plan |

---

## Configuration

All configuration is in `backend/.env`:

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_MODEL` | Main LLM model | `google/gemini-2.0-flash-001` |
| `FAST_MODEL` | Fast/cheap model for parallel calls | `google/gemini-2.0-flash-001` |
| `LLM_BASE_URL` | LLM API endpoint | `https://openrouter.ai/api/v1` |
| `LLM_API_KEY` | OpenRouter API key | — |
| `EMBEDDING_MODEL` | Embedding model | `openai/text-embedding-3-small` |
| `EMBEDDING_BASE_URL` | Embedding API endpoint | `https://models.github.ai/inference` |
| `EMBEDDING_API_KEY` | GitHub Models API key | — |
| `SUPABASE_URL` | Supabase project URL | — |
| `SUPABASE_KEY` | Supabase anon key | — |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | — |

---

## Adding New Laws

1. Place the PDF in `backend/law_docs/`
2. Add the entry to `LAW_DOCS` in `scripts/ingest_laws.py`
3. Add the act name to `AVAILABLE_LAW_DOCS` in `app/services/agent_service.py`
4. Run: `python scripts/ingest_laws.py`

The script handles text extraction, chunking by chapter/section, embedding, and storage in Supabase.

---

## Design Decisions

- **OpenRouter** for LLM (flexible model switching)
- **GitHub Models** for embeddings (free tier available)
- **Parallel LLM calls** for speed (2 phases instead of 6 sequential calls)
- **Brutally honest readiness scoring** — vague descriptions get low scores
- **Placeholders in documents** — names/addresses are `[BRACKETS]`, never hallucinated
- **Simple language** — all outputs use plain English anyone can understand

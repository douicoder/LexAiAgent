# LexAiAgent

**AI-Powered Legal Aid for Everyone**

> Describe your legal problem in plain language. Get instant analysis, relevant laws, evidence guidance, legal documents, and a step-by-step action plan — all powered by AI.

---

## What is LexAiAgent?

LexAiAgent is a web-based legal aid system that helps ordinary people understand their legal rights and take action. No lawyers, no legal jargon, no expensive consultations.

**How it works:**
1. You describe your legal problem in your own words
2. The system classifies your case and finds relevant Indian laws
3. It assesses how ready your case is and tells you what evidence you need
4. It generates legal notices, demand letters, and supporting documents
5. It gives you a prioritized action plan

**Currently supports:** Indian property and tenancy law
- Model Tenancy Act 2021
- Transfer of Property Act 1882
- Registration Act 1908

---

## Demo

**Try it:** http://localhost:5000/demo/

1. Type a legal problem or pick a preset scenario
2. Click **Improve Query** to enhance your description
3. Click **Analyze Case** to run the full analysis
4. Review the readiness score and evidence checklist
5. Check/uncheck evidence items and click **Update Score**
6. Edit documents in the tabs and download as PDF

---

## How It Works

### The 4-Phase Pipeline

```
Your Description
       │
       ▼
┌─────────────────────┐
│  Phase 1: Classify   │  What type of case? Is the input clear enough?
│  (2 parallel LLMs)  │  If vague → clarifying questions
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 2: RAG        │  Search 3 Indian law acts for relevant sections
│  Vector + BM25       │  using semantic search + keyword matching
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 3: Generate   │  Generate evidence checklist, legal notice,
│  (4 parallel LLMs)   │  supporting docs, and action plan
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 4: Assemble   │  Parse results, score readiness, build response
└─────────┬───────────┘
          │
          ▼
    Complete Case Analysis
```

**Total time:** ~15-25 seconds

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Flask, TailwindCSS, Vanilla JS |
| **Backend** | FastAPI, Python 3.11 |
| **LLM** | Google Gemini 2.0 Flash (via OpenRouter) |
| **Embeddings** | OpenAI text-embedding-3-small (via GitHub Models) |
| **Database** | Supabase (PostgreSQL + pgvector) |
| **PDF Generation** | ReportLab |

---

## Project Structure

```
LexAiAgent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Environment variables
│   │   ├── api/
│   │   │   └── demo.py          # API endpoints
│   │   ├── services/
│   │   │   ├── agent_service.py # Core AI pipeline
│   │   │   ├── rag_service.py   # Law search (RAG)
│   │   │   └── pdf_service.py   # PDF generation
│   │   ├── dto/
│   │   │   └── agent_dto.py     # Data models
│   │   └── helpers/
│   │       ├── legal_helper.py  # Prompts & templates
│   │       └── text_helper.py   # Language detection
│   ├── scripts/
│   │   └── ingest_laws.py       # Law PDF ingestion
│   ├── law_docs/                # Source law PDFs
│   ├── .env                     # Secrets (not in git)
│   └── requirements.txt
│
├── frontend/
│   ├── app.py                   # Flask entry point
│   ├── routes/
│   │   └── demo.py              # Demo route
│   ├── templates/
│   │   └── demo/
│   │       └── demo.html        # Main UI (SPA)
│   └── requirements.txt
│
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Supabase account (free tier works)
- OpenRouter API key (for LLM)
- GitHub PAT (for embeddings)

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your API keys (see Configuration below)

# Run the server
uvicorn app.main:app --reload --port 8002
```

### 2. Frontend Setup

```bash
cd frontend

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```

### 3. Law Ingestion (One-time)

```bash
cd backend

# Place your law PDFs in law_docs/
python scripts/ingest_laws.py
```

### 4. Open

- **Frontend:** http://localhost:5000/demo/
- **Backend API docs:** http://localhost:8002/docs

---

## Configuration

### Backend `.env`

```env
# LLM (OpenRouter)
LLM_MODEL=google/gemini-2.0-flash-001
FAST_MODEL=openai/gpt-oss-20b:free
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your-openrouter-api-key

# Embeddings (GitHub Models)
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_BASE_URL=https://models.github.ai/inference
EMBEDDING_API_KEY=your-github-pat

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
```

### Supabase Setup

1. Create a new Supabase project
2. Run the SQL in `backend/supabase_script.txt` to create tables
3. Enable the `vector` extension for pgvector
4. Run `python scripts/apply_schema.py` to create the RPC function

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/demo/improve-prompt` | Enhance a legal description |
| `POST` | `/api/v1/demo/analyze` | Full legal analysis |
| `POST` | `/api/v1/demo/update-evidence` | Update score with new evidence |
| `POST` | `/api/v1/demo/pdf` | Generate PDF legal notice |

---

## Key Features

- **Brutally honest readiness scoring** — no free points, reflects actual case completeness
- **Evidence checklist** — tracks what you have and what's missing
- **Document editing** — edit generated documents before downloading
- **Parallel LLM calls** — 6 LLM calls completed in ~15-25 seconds
- **RAG-powered law search** — semantic vector search + BM25 keyword matching
- **Multilingual** — supports Hindi input (auto-translated)

---

## Known Limitations

- Only 3 Indian law acts are indexed (property/tenancy)
- No authentication or user accounts
- Demo mode only — no case persistence
- Rate limits on free-tier APIs may cause delays
- Read-only law corpus — requires re-ingestion for new laws

---

## Future Scope

- More laws: criminal, consumer, employment, family law
- Multi-language support: Hindi, Tamil, Bengali, etc.
- Voice input for describing legal problems
- Conversational chat interface
- Case management and tracking
- Mobile app for wider accessibility

---

## License

This project is for educational and demonstration purposes.

---

Built for the community. Legal aid should be free and accessible to everyone.

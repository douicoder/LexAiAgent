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

**Currently loaded:** Indian property and tenancy law
- Model Tenancy Act 2021
- Transfer of Property Act 1882
- Registration Act 1908

**Extensible:** Drop any Indian law PDF into `backend/law_docs/` and run `python scripts/ingest_laws.py` — no code changes needed.

---

## Quick Start

### Prerequisites

| Requirement | Why | Get it |
|-------------|-----|--------|
| Python 3.11+ | Runtime | [python.org](https://python.org) |
| OpenRouter API key | Powers the LLM (Gemini Flash) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| GitHub Personal Access Token | Powers embeddings | [github.com/settings/tokens](https://github.com/settings/tokens) |
| Supabase account | Database + law storage | [supabase.com](https://supabase.com) (free tier works) |

### Step 1 — Clone the repo

```bash
git clone https://github.com/douicoder/LexAiAgent.git
cd LexAiAgent
```

### Step 2 — Backend setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Copy the example env file and fill in your keys
copy .env.example .env         # Windows
# cp .env.example .env         # Mac/Linux
```

Now edit `.env` and fill in your actual API keys:

```env
# LLM — paste your OpenRouter API key
LLM_API_KEY=sk-or-xxxxxxxxxxxx

# Embeddings — paste your GitHub PAT
EMBEDDING_API_KEY=ghp_xxxxxxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_TOKEN_2=ghp_xxxxxxxxxxxx

# Supabase — paste your project credentials
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8002
```

Backend is running at http://localhost:8002

### Step 3 — Frontend setup

Open a **new terminal**:

```bash
cd frontend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Start the frontend
python app.py
```

Frontend is running at http://localhost:5000/demo/

### Step 4 — Supabase database setup

1. Go to your [Supabase dashboard](https://supabase.com/dashboard)
2. Open the SQL Editor
3. Paste and run the contents of `backend/supabase_script.txt`
4. This creates the `law_chunks` table and the `match_law_chunks` RPC function

### Step 5 — Ingest law documents (one-time)

```bash
cd backend

# Place your law PDFs in the law_docs/ folder
# Only law documents go here — nothing else

# Run ingestion:
python scripts/ingest_laws.py
```

This reads the PDFs, extracts text, generates embeddings, and stores them in Supabase. Takes ~2-5 minutes depending on PDF size.

### Step 6 — Open and use

- **Frontend:** http://localhost:5000/demo/
- **Backend API docs (Swagger):** http://localhost:8002/docs

---

## How to Use

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
│  (2 parallel LLMs)  │  If vague → returns "Insufficient data to proceed"
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Phase 2: RAG        │  Search law acts for relevant sections
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
│   │   ├── ingest_laws.py       # Law PDF ingestion (run this)
│   │   └── apply_schema.py      # Supabase RPC setup
│   ├── law_docs/                # Law PDFs only (not in git)
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

## Configuration Reference

All configuration lives in `backend/.env`. See `backend/.env.example` for the full template.

| Key | Description | Where to get |
|-----|-------------|--------------|
| `LLM_API_KEY` | OpenRouter API key | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `LLM_BASE_URL` | OpenRouter endpoint | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Main LLM model | `google/gemini-2.0-flash-001` |
| `FAST_MODEL` | Fast LLM model | `openai/gpt-oss-20b:free` |
| `EMBEDDING_API_KEY` | GitHub PAT for embeddings | [github.com/settings/tokens](https://github.com/settings/tokens) |
| `EMBEDDING_BASE_URL` | GitHub Models endpoint | `https://models.github.ai/inference` |
| `SUPABASE_URL` | Supabase project URL | Supabase dashboard → Settings → API |
| `SUPABASE_KEY` | Supabase anon key | Supabase dashboard → Settings → API |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | Supabase dashboard → Settings → API |

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

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'fitz'` | Run `pip install PyMuPDF` (the package name is PyMuPDF, not fitz) |
| Backend crashes on startup | Check `.env` — all keys must be filled in |
| `429 Too Many Requests` | OpenRouter free tier rate limit. Wait 30s and retry |
| No law sections found | Run `python scripts/ingest_laws.py` to ingest law PDFs |
| PDF download fails | Ensure `legal-notices` bucket exists in Supabase |
| Frontend can't connect | Ensure backend is running on port 8002 |

---

## Deploy

### Option A: Backend on Render + Frontend on Vercel (Recommended)

**Backend (Render):**

1. Go to [render.com](https://render.com) and sign up
2. Click **New → Web Service**
3. Connect your GitHub repo
4. Configure:
   - **Name:** `lexaiagent-backend`
   - **Runtime:** Python
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Go to **Environment** tab and add all keys from `backend/.env`:
   ```
   LLM_API_KEY=sk-or-...
   LLM_BASE_URL=https://openrouter.ai/api/v1
   LLM_MODEL=google/gemini-2.0-flash-001
   FAST_MODEL=openai/gpt-oss-20b:free
   EMBEDDING_API_KEY=ghp_...
   EMBEDDING_BASE_URL=https://models.github.ai/inference
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_KEY=eyJ...
   SUPABASE_SERVICE_KEY=eyJ...
   GITHUB_TOKEN=ghp_...
   GITHUB_TOKEN_2=ghp_...
   ```
6. Click **Create Web Service**
7. Wait for deploy — your backend is live at `https://lexaiagent-backend.onrender.com`

**Frontend (Vercel):**

1. Update `public/index.html` line 6 with your Render URL:
   ```html
   <meta name="api-url" content="https://lexaiagent-backend.onrender.com/api/v1/demo">
   ```
2. Push to GitHub
3. Go to [vercel.com/new](https://vercel.com/new) → Import repo → Deploy
4. Your frontend is live at `https://your-project.vercel.app`

---

### Option B: Everything on Vercel

Both frontend and backend on Vercel (serverless functions).

**Note:** Vercel free tier has 10s timeout. Analysis takes 15-25s. May need Pro plan ($20/mo).

1. Add environment variables on Vercel (Settings → Environment Variables)
2. Push and deploy — Vercel auto-detects the config

---

## Known Limitations

- Demo mode only — no authentication, no case persistence
- Rate limits on free-tier APIs may cause delays
- Law corpus must be re-ingested when new PDFs are added

---

## Future Scope

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

# LexAgent Backend — Architecture & Design

## 1. Overview

LexAgent is a legal AI assistant specializing in Indian property and tenancy law. The backend is a **FastAPI** application that orchestrates a multi-agent LLM pipeline, a hybrid RAG search over Indian law texts, and a local auth system — all exposed via REST endpoints.

**Stack**: FastAPI + SQLAlchemy (async) + SQLite/PostgreSQL + OpenAI SDK (via GitHub Models) + Supabase (vector storage + auth proxy).

---

## 2. Directory Layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, routers, CORS, startup
│   ├── config.py               # Settings from .env (pydantic-settings)
│   ├── database.py             # SQLAlchemy async engine, session, table creation
│   ├── api/                    # Route handlers
│   │   ├── auth.py             #  POST /register, /login, GET /me
│   │   ├── cases.py            #  CRUD /cases, POST /{id}/pdf
│   │   ├── agent.py            #  POST /agent/analyze, /agent/chat
│   │   ├── documents.py        #  GET /documents/search
│   │   └── voice.py            #  POST /voice/transcribe (WAV → whisper → text)
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── user.py             #  users table
│   │   ├── case.py             #  cases table (all analysis results)
│   │   └── document.py         #  law_chunks table (ingested law texts + embeddings)
│   ├── dto/                    # Pydantic request/response schemas
│   │   ├── auth_dto.py
│   │   ├── case_dto.py
│   │   ├── agent_dto.py
│   │   └── document_dto.py
│   ├── services/               # Business logic
│   │   ├── agent_service.py    #  Multi-round LLM pipeline
│   │   ├── case_service.py     #  Case CRUD + orchestration
│   │   ├── rag_service.py      #  Hybrid vector+BM25 search
│   │   └── pdf_service.py      #  ReportLab PDF generation + Supabase Storage upload
│   ├── helpers/                # Utility classes
│   │   ├── auth_helper.py      #  JWT creation/validation, Supabase proxy
│   │   ├── legal_helper.py     #  System prompts, notice templates, deadlines
│   │   └── text_helper.py      #  Hindi detection, translation, text cleaning
│   ├── interfaces/             # Abstract base classes (contracts)
│   │   ├── i_agent_service.py
│   │   ├── i_case_service.py
│   │   ├── i_rag_service.py
│   │   └── i_pdf_service.py
│   └── mapper/
│       └── auto_mapper.py      #  Model → DTO converters
├── requirements.txt
├── .env.example
└── Dockerfile
```

---

## 3. Authentication Flow

### 3.1 Design Decision: Local JWT, not Supabase JWT

Supabase returns ES256-signed JWTs. Python's `python-jose` HS256 decoder cannot verify these. Instead:

1. **Register / Login** — `AuthHelper.supabase_sign_up()` / `supabase_sign_in()` delegates user creation/verification to Supabase Auth (handles email, password hashing, duplicate checks).
2. **Token Issuance** — `AuthHelper.supabase_auth_response()` extracts the Supabase `user.id`, then issues a **local HS256 JWT** via `AuthHelper.create_jwt(user_id)`. The Supabase JWT is discarded — only our local JWT reaches the frontend.
3. **Request Auth** — Every protected endpoint uses `AuthHelper.get_current_user_id` (a FastAPI `Depends`). This calls `AuthHelper.decode_jwt()` locally — **no HTTP call to Supabase per request**.

### 3.2 Token Payload

```json
{
  "sub": "<user-uuid>",
  "exp": "<7-days-from-now>"
}
```

Signed with `JWT_SECRET` using HS256.

### 3.3 Auth Endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `POST /api/v1/auth/register` | None | Creates Supabase user, returns local JWT |
| `POST /api/v1/auth/login` | None | Verifies credentials via Supabase, returns local JWT |
| `GET /api/v1/auth/me` | Bearer token | Fetches profile (still calls Supabase HTTP) |

---

## 4. The Case Pipeline (3-Round Agent)

This is the core intelligence. When `POST /api/v1/cases` is called, `CaseService.create_case` triggers `AgentService.analyze_case`:

```
User submits description
        │
        ▼
┌─────────────────────┐
│  Round 1: Classify  │  GPT-4o (FAST_MODEL)
│  case_type, severity │  JSON output
│  reasoning           │
└─────────┬───────────┘
          │ case_type, severity, reasoning
          ▼
┌─────────────────────┐
│  Round 2: Search    │  GPT-4o (FAST_MODEL)
│  Generate query     │  → RAG search (top_k=5)
└─────────┬───────────┘
          │ law sections + classification
          ▼
┌─────────────────────┐
│  Round 3: Generate  │  LLM_MODEL (default: Phi-4-reasoning)
│  ai_message +       │  JSON output via FINAL_JSON: marker
│  summary + notice   │
│  next_steps +       │
│  clarifying_questions│
└─────────┬───────────┘
          │
          ▼
   Saved to DB + returned as CaseResponseDTO
```

### 4.1 Round 1 — Classify (GPT-4o)

A cheap, fast call to categorize the problem. Output:

```json
{
  "case_type": "tenancy_dispute",
  "severity": "high",
  "reasoning": "Landlord refusing deposit return after vacating"
}
```

**Case types**: `tenancy_dispute` | `property_ownership` | `property_registration` | `other`

### 4.2 Round 2 — Search Query (GPT-4o)

Takes the classification and generates a targeted legal search query. Output:

```json
{
  "query": "rent deposit refund Transfer of Property Act 1882 section"
}
```

This query is fed to `RagService.search()` which returns the top 5 matching law sections.

### 4.3 Round 3 — Generate (Phi-4-reasoning / GPT-4o)

The slow, expensive reasoning call. Given the original problem + classification + law sections, generates a comprehensive JSON response. Uses a **`FINAL_JSON:` marker** to extract structured output from reasoning models (which embed JSON in chain-of-thought).

Output fields:
- `ai_message` — warm, conversational explanation for the chat UI
- `summary` — 2-3 sentence plain-language summary
- `legal_notice_draft` — full formal legal notice text
- `next_steps` — structured action items with optional action buttons
- `clarifying_questions` — 2-3 questions to strengthen the notice
- `action_buttons` — quick-reply buttons matching the clarifying questions

### 4.4 Chat Mode

`POST /api/v1/agent/chat` is a simpler single-round call that:
1. Includes the current `legal_notice_draft` in the system context
2. Detects if the user is answering clarifying questions (updates notice)
3. Detects edit requests like "make deadline 30 days" (updates notice)
4. Returns structured JSON with `reply`, `updated_notice`, `action_buttons`, `clarifying_questions`

No RAG search — chat works with the existing draft and conversation history.

### 4.5 JSON Extraction Strategy

`_extract_json()` scans the LLM response from **right to left** to find the last complete JSON object. This is necessary because reasoning models (like Phi-4) embed JSON within chain-of-thought text. The function properly handles:
- Escaped characters
- Nested strings
- Multiple brace levels

---

## 5. PDF Generation & Storage

### 5.1 PDF Generation (ReportLab)

`PdfService.generate_legal_notice()` creates a professional legal notice PDF using ReportLab's `platypus` framework:

- **Header**: "LEGAL NOTICE" title with horizontal rule
- **Parties**: TO (recipient) and FROM (sender) fields with names and addresses
- **Body**: Full legal notice text wrapped in justified paragraphs
- **Legal Provisions**: Table of relevant law sections
- **Signature**: Sender name, address, and date
- **Footer**: Page numbers on every page

### 5.2 Supabase Storage Upload

`PdfService.upload_to_storage()` uploads the generated PDF to Supabase Storage:

- **Bucket**: `legal-notices` (configured by `SUPABASE_STORAGE_BUCKET`)
- **Auth**: Uses `service_role` key (admin client) — anon key cannot write to storage
- **File path**: `notices/{case_id}/{filename}.pdf`
- **After upload**: Updates case with `pdf_url`, `pdf_id`, sets `status = "notice_generated"`

### 5.3 Dual Supabase Clients

`PdfService` initializes two clients:

| Client | Key | Purpose |
|---|---|---|
| `self.supabase` | anon key (`SUPABASE_KEY`) | DB reads only |
| `self.supabase_admin` | service_role key (`SUPABASE_SERVICE_KEY`) | Storage uploads only |

### 5.4 Endpoint

`POST /api/v1/cases/{case_id}/pdf` — Protected; fetches case (ownership check), verifies `legal_notice_draft` exists, calls `PdfService.generate_pdf()`, returns `PdfResponseDTO` with `pdf_url`, `pdf_id`, `generated_at`.

---

## 6. Voice Transcription

### 6.1 Endpoint

`POST /api/v1/voice/transcribe` — Accepts multipart form (WAV file + optional language hint). No auth required. Returns `{ transcript, detected_language, confidence }`.

### 6.2 Implementation

- HuggingFace `transformers` pipeline with `openai/whisper-base` (lazy-loaded, globally cached)
- WAV files read via `scipy.io.wavfile` (no ffmpeg dependency)
- First inference: ~7s model load + ~33s transcription (CPU); subsequent calls warm

### 6.3 Design Decision: Local Model over API

GitHub Models API does not support audio transcription. Local Whisper eliminates API dependency, works offline, and supports Hindi natively. The `scipy.io.wavfile` workaround avoids ffmpeg.

### 6.4 Error Handling

- 400 for non-WAV formats
- 503 if model fails to load
- Graceful handling of silent audio

---

## 7. RAG System (Hybrid Search)

### 7.1 Architecture

```
User query
    │
    ▼
┌────────────────┐
│  Embed query    │  OpenAI text-embedding-3-small (1536-d)
│  via GitHub AI  │
└───────┬────────┘
        │ vector
        ▼
┌─────────────────────────────────────┐
│  Fetch ALL law_chunks from Supabase │
│  (act_name, chunk_text, embedding,  │
│   metadata)                         │
└───────┬────────────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Cosine similarity  │  vector_score per chunk
│  on every row       │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  BM25 keyword score │  lexical_score per chunk
│  (if hybrid enabled)│  (squashed via sigmoid: s/(s+1))
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  Fuse:              │
│  score = VW * vec   │  VW = vector_weight (default 0.7)
│       + (1-VW)*bm25 │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  Optional rerank    │  CrossEncoder on top 2*k candidates
│  (CrossEncoder)     │  (ms-marco-MiniLM-L-6-v2)
└───────┬─────────────┘
        │
        ▼
   Return top_k results
```

### 7.2 Hybrid Fusion Formula

```
final_score = vector_weight × cosine_similarity + (1 - vector_weight) × sigmoid(bm25_score)
```

Where `sigmoid(bm25) = bm25 / (bm25 + 1.0)` squashes unbounded BM25 scores into [0, 1).

### 7.3 Search Parameters

| Parameter | Default | Description |
|---|---|---|
| `top_k` | 5 | Max results to return |
| `acts` | None | Filter by act name(s) |
| `min_relevance_score` | 0.0 | Minimum fused score threshold |
| `use_hybrid` | True | Enable BM25 blending |
| `use_rerank` | False | Enable CrossEncoder reranking (slow) |
| `vector_weight` | 0.7 | Weight for vector vs BM25 |

### 7.4 BM25 Lazy Loading

BM25 index is built on first search call by fetching all `chunk_text` from Supabase. This avoids startup delay.

### 7.5 Embedding

Uses `OpenAI` client pointed at GitHub Models API (`https://models.github.ai/inference`) with `text-embedding-3-small` (1536 dimensions).

---

## 8. Severity → Response Deadline Mapping

| Severity | Deadline (days) | Use case |
|---|---|---|
| `urgent` | 7 | Imminent court hearing, eviction notice |
| `high` | 15 | Active dispute, money involved |
| `medium` | 30 | Documentation issue, no immediate threat |
| `low` | 60 | Informational, general advice |

Defined in `LegalHelper.get_response_deadline()`.

---

## 9. API Endpoints Summary

All under `/api/v1`.

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Register, returns JWT |
| POST | `/auth/login` | No | Login, returns JWT |
| GET | `/auth/me` | Yes | User profile |

### Cases

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/cases` | Yes | Create case (triggers agent pipeline, returns analyzed result) |
| GET | `/cases` | Yes | List user's cases |
| GET | `/cases/{id}` | Yes | Get case detail |
| DELETE | `/cases/{id}` | Yes | Delete case |
| POST | `/cases/{id}/pdf` | Yes | Generate & upload PDF legal notice |

### Agent

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/agent/analyze` | Yes | Run full analysis (used internally by cases too) |
| POST | `/agent/chat` | Yes | Conversational follow-up with notice editing |

### Documents

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/documents/search` | No | Search law texts with hybrid RAG |

### Voice

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/voice/transcribe` | No | Transcribe WAV audio to text (Whisper) |

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Health check |

---

## 10. Data Models

### Case (`cases` table)

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → users | |
| `description` | Text | Original user description |
| `language` | String | `"en"` or `"hi"` |
| `case_type` | String? | Classification result |
| `severity` | String? | `low/medium/high/urgent` |
| `status` | String | `processing` → `analyzed` |
| `relevant_sections` | JSON | Law sections found |
| `summary` | Text? | Plain-language summary |
| `next_steps` | JSON | Array of `NextStep` objects |
| `agent_reasoning` | Text? | Full reasoning trace |
| `legal_notice_draft` | Text? | Generated notice text |
| `ai_message` | Text? | Conversational message for chat UI |
| `clarifying_questions` | JSON | Array of `ClarifyingQuestion` |
| `action_buttons` | JSON | Array of `ActionButton` |
| `pdf_url` | String? | Supabase Storage public URL |
| `pdf_id` | String? | Supabase Storage file ID |
| `created_at` | DateTime | |
| `updated_at` | DateTime? | |

**Note**: All `JSON` columns store lists as JSON arrays. SQLAlchemy's `JSON` type is used instead of `JSONB` because the app uses SQLite in development (SQLite lacks JSONB support).

### User (`users` table)

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `email` | String unique | |
| `hashed_password` | String | bcrypt hash via passlib |
| `full_name` | String | |
| `preferred_language` | String | `"en"` or `"hi"` |

### LawChunk (`law_chunks` table — Supabase)

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `act_name` | String | e.g. "Transfer of Property Act 1882" |
| `section_number` | String? | e.g. "Section 106" |
| `section_title` | String? | e.g. "Notice to quit" |
| `chunk_text` | Text | Full text of the chunk |
| `embedding` | Vector(1536) | OpenAI embedding |
| `metadata` | JSON | Additional metadata |

---

## 11. DTO Layer (Request/Response Schemas)

The DTO layer is the public contract between frontend and backend. Key schemas:

### agent_dto.py — Chat UI Models

```
ClarifyingQuestion { question, key }
ActionButton       { label, message, style("default"|"primary") }
NextStep           { number, text, action_label, action_message }
```

These power the conversational UI: clarifying questions appear as prompts, action buttons as quick-reply chips, next steps as structured cards.

### case_dto.py — API Response Models

`CaseResponseDTO` is the main output shape from `POST /cases`. It includes:
- `next_steps: list[NextStep]` — structured action items, not plain strings
- `ai_message` — the conversational message for the chat bubble
- `clarifying_questions` and `action_buttons` — for interactive follow-up
- `relevant_sections: list[LegalSectionDTO]` — law sections with `act`, `section`, `title`, `excerpt`, `relevance_score`

`CaseDetailDTO` extends `CaseResponseDTO` with `description`, `agent_reasoning`, `legal_notice_draft`, and `pdf_url`.

### auth_dto.py — Auth Schemas

- `RegisterDTO` — email, password (min 8 chars), full_name, preferred_language enum
- `LoginDTO` — email, password
- `AuthResponseDTO` — email, full_name, access_token (our local JWT), token_type

---

## 12. Key Design Decisions

### 12.1 Why a 3-round pipeline instead of a single LLM call?

| Round | Model | Cost | Purpose |
|---|---|---|---|
| 1. Classify | GPT-4o (fast) | Cheap | Extract structured classification |
| 2. Search | GPT-4o (fast) | Cheap | Generate targeted legal query |
| 3. Generate | Phi-4-reasoning (slow) | Expensive | Deep legal reasoning + notice drafting |

Separation of concerns: classification and query generation are simple enough for a cheap model. The expensive reasoning model only runs once, with full context already prepared.

### 12.2 Why local JWT instead of Supabase JWT?

Supabase issues ES256 JWTs. The `python-jose` library only supports HS256/RS256 decoding without extra dependencies. Rather than adding EC crypto dependencies and verifying Supabase JWTs on every request (which also requires fetching Supabase's JWKS), we issue our own HS256 JWT at login/register time. This eliminates an HTTP roundtrip per request and keeps the dependency footprint small.

### 12.3 Why fetch ALL law chunks instead of using pgvector index?

The current implementation fetches all rows and computes cosine similarity in Python. This works for small datasets (<10k chunks) but won't scale. A production version should use pgvector's `ORDER BY embedding <=> $1 LIMIT n` for approximate nearest neighbor search. The `LawChunk` model already imports `pgvector.sqlalchemy.Vector` — the infrastructure is ready.

### 12.4 Why SQLite in development?

`DATABASE_URL=sqlite+aiosqlite:///./lexagent.db` enables zero-setup local development. The `create_tables()` function handles SQLite's lack of schema migration by creating tables individually. In production, switch to PostgreSQL with `asyncpg`.

### 12.5 BM25 squashing function

BM25 scores are unbounded (can be >100). The `_squash_bm25` function (`x / (x + 1.0)`) maps them to [0, 1) so they can be fused with cosine similarity scores via weighted average.

---

## 13. Configuration (.env)

| Key | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | GitHub Personal Access Token for GitHub Models API |
| `SUPABASE_URL` | — | Supabase project URL (for auth + law_chunks) |
| `SUPABASE_KEY` | — | Supabase anon/public key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./lexagent.db` | SQLAlchemy async connection string |
| `JWT_SECRET` | `change-this-secret` | HMAC secret for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | JWT expiry |
| `APP_ENV` | `development` | Controls SQLAlchemy echo logging |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `LLM_MODEL` | `gpt-4o` | Overridden in .env to `microsoft/Phi-4-reasoning` |
| `SUPABASE_SERVICE_KEY` | — | Supabase service_role key (for Storage uploads only) |
| `SUPABASE_STORAGE_BUCKET` | `legal-notices` | Supabase Storage bucket for generated PDFs |

---

## 14. Running Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Swagger UI: `http://localhost:8000/docs`

### First-time setup

1. Ingest law documents into Supabase `law_chunks` table (run `ingest_laws.py` in `scripts/`)
2. Delete `lexagent.db` if schema changed (new columns added to Case model)
3. Server auto-creates tables on startup
4. First voice transcription downloads `openai/whisper-base` (~150MB) from HuggingFace — ensure internet access

### Testing the full flow

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123","full_name":"Test User"}'

# Save the access_token, then:
curl -X POST http://localhost:8000/api/v1/cases \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"description":"My landlord is refusing to return my Rs 50,000 deposit","language":"en"}'

# Generate PDF from case (requires legal_notice_draft to exist)
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/pdf \
  -H "Authorization: Bearer <token>"

# Voice transcription
curl -X POST http://localhost:8000/api/v1/voice/transcribe \
  -F "file=@recording.wav" \
  -F "language=en"
```

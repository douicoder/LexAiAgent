# LexAgent API Documentation

**Base URL**: `http://localhost:8000/api/v1`

**Auth**: All protected endpoints require a `Bearer` token from `/auth/login` or `/auth/register`. Send as header: `Authorization: Bearer <token>`

---

## Auth

### POST /auth/register

Create a new user account. Delegates to Supabase Auth for password hashing, returns a local HS256 JWT.

**Request** — `RegisterDTO`

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | EmailStr | Yes | Valid email address |
| `password` | string | Yes | Min 8 characters |
| `full_name` | string | Yes | User's display name |
| `preferred_language` | `"en"` \| `"hi"` | No | Default: `"en"` |

```json
{
  "email": "user@example.com",
  "password": "mypassword123",
  "full_name": "Rahul Sharma",
  "preferred_language": "en"
}
```

**Response** — `AuthResponseDTO`

| Field | Type | Description |
|---|---|---|
| `email` | string | User email |
| `full_name` | string | User display name |
| `access_token` | string | HS256 JWT (expires in 7 days) |
| `token_type` | string | Always `"bearer"` |

```json
{
  "email": "user@example.com",
  "full_name": "Rahul Sharma",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"mypassword123","full_name":"Rahul Sharma"}'
```

### POST /auth/login

Authenticate existing user. Verifies credentials via Supabase Auth, returns a local HS256 JWT.

**Request** — `LoginDTO`

| Field | Type | Required |
|---|---|---|
| `email` | EmailStr | Yes |
| `password` | string | Yes |

```json
{
  "email": "user@example.com",
  "password": "mypassword123"
}
```

**Response** — `AuthResponseDTO` (same as register)

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"mypassword123"}'
```

### GET /auth/me

Fetch current user profile from Supabase.

**Auth**: Bearer token required

**Response** — `UserProfileDTO`

| Field | Type | Description |
|---|---|---|
| `email` | string | User email |
| `full_name` | string | User display name |
| `preferred_language` | `"en"` \| `"hi"` | Language preference |
| `case_count` | int | Number of cases for this user |

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <token>"
```

---

## Cases

### POST /cases

Create a new case. Triggers the full 3-round agent pipeline: classify → search → generate. Returns the analyzed result with legal notice draft, next steps, and clarifying questions.

**Auth**: Bearer token required

**Request** — `CreateCaseDTO`

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string | Yes | User's legal problem description |
| `language` | `"en"` \| `"hi"` | No | Default: `"en"` |

```json
{
  "description": "My landlord is refusing to return my Rs 50,000 deposit after I vacated the flat 3 months ago.",
  "language": "en"
}
```

**Response** — `CaseResponseDTO`

| Field | Type | Description |
|---|---|---|
| `case_id` | string (UUID) | Unique case identifier |
| `status` | `CaseStatusEnum` | `processing` → `analyzed` → `notice_generated` |
| `case_type` | `CaseTypeEnum` or null | `tenancy_dispute`, `property_ownership`, `property_registration`, `other` |
| `severity` | `SeverityEnum` or null | `low`, `medium`, `high`, `urgent` |
| `relevant_sections` | list\[LegalSectionDTO\] | Law sections found by RAG search |
| `summary` | string or null | Plain-language summary |
| `next_steps` | list\[NextStep\] | Structured action items |
| `pdf_ready` | bool | Whether a PDF has been generated |
| `created_at` | datetime or null | ISO 8601 |
| `ai_message` | string or null | Conversational message for chat UI |
| `clarifying_questions` | list\[ClarifyingQuestion\] | Follow-up questions to strengthen notice |
| `action_buttons` | list\[ActionButton\] | Quick-reply button suggestions |

```bash
curl -X POST http://localhost:8000/api/v1/cases \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"description":"My landlord is refusing to return my Rs 50,000 deposit","language":"en"}'
```

### GET /cases

List all cases for the authenticated user.

**Auth**: Bearer token required

**Response** — `CaseListResponseDTO`

| Field | Type | Description |
|---|---|---|
| `cases` | list\[CaseResponseDTO\] | Array of case summaries |
| `total` | int | Total count |

```bash
curl http://localhost:8000/api/v1/cases \
  -H "Authorization: Bearer <token>"
```

### GET /cases/{case_id}

Get full case detail including the legal notice draft and reasoning trace.

**Auth**: Bearer token required

**Response** — `CaseDetailDTO` (extends CaseResponseDTO)

| Field | Type | Description |
|---|---|---|
| *inherits CaseResponseDTO* | | All CaseResponseDTO fields |
| `description` | string | Original user description |
| `agent_reasoning` | string or null | Full reasoning trace from the agent |
| `legal_notice_draft` | string or null | Generated legal notice text |
| `pdf_url` | string or null | Supabase Storage URL of generated PDF |

```bash
curl http://localhost:8000/api/v1/cases/<case_id> \
  -H "Authorization: Bearer <token>"
```

### DELETE /cases/{case_id}

Delete a case.

**Auth**: Bearer token required

```bash
curl -X DELETE http://localhost:8000/api/v1/cases/<case_id> \
  -H "Authorization: Bearer <token>"
```

### POST /cases/{case_id}/pdf

Generate a PDF legal notice from the case's `legal_notice_draft`. Uploads to Supabase Storage and updates the case status to `notice_generated`.

**Auth**: Bearer token required

**Response** — `PdfResponseDTO`

| Field | Type | Description |
|---|---|---|
| `pdf_url` | string | Public Supabase Storage URL |
| `pdf_id` | string | Storage file ID (same as case_id) |
| `generated_at` | string | ISO 8601 timestamp |

```bash
curl -X POST http://localhost:8000/api/v1/cases/<case_id>/pdf \
  -H "Authorization: Bearer <token>"
```

---

## Agent

### POST /agent/analyze

Run the full 3-round legal analysis pipeline on a description. Returns classification, RAG results, and a generated legal notice. Used internally by `POST /cases` but also exposed directly.

**Auth**: Bearer token required

**Request** — `AnalyzeRequestDTO`

| Field | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | Yes | UUID for tracking |
| `description` | string | Yes | Legal problem description |
| `user_name` | string | Yes | Sender name for notice |
| `opponent_name` | string | Yes | Recipient name for notice |
| `opponent_address` | string | Yes | Recipient address for notice |
| `language` | string | No | `"en"` or `"hi"` |

```json
{
  "case_id": "550e8400-e29b-41d4-a716-446655440000",
  "description": "Landlord refusing deposit return",
  "user_name": "Rahul Sharma",
  "opponent_name": "Mr. Verma",
  "opponent_address": "42, MG Road, Mumbai",
  "language": "en"
}
```

**Response** — `AnalyzeResponseDTO`

| Field | Type | Description |
|---|---|---|
| `case_type` | string | Classification result |
| `severity` | string | `low`, `medium`, `high`, `urgent` |
| `relevant_sections` | list | Law sections found |
| `legal_notice_draft` | string | Generated formal notice text |
| `summary` | string | Plain-language summary |
| `next_steps` | list\[NextStep\] | Action items |
| `reasoning_trace` | string | Full agent reasoning |
| `clarifying_questions` | list\[ClarifyingQuestion\] | Follow-up questions |
| `action_buttons` | list\[ActionButton\] | Quick-reply buttons |
| `ai_message` | string | Conversational message |

```bash
curl -X POST http://localhost:8000/api/v1/agent/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"case_id":"...","description":"Landlord refusing deposit","user_name":"Rahul","opponent_name":"Mr. Verma","opponent_address":"42 MG Road, Mumbai"}'
```

### POST /agent/chat

Conversational follow-up with an existing case. History is loaded server-side from Supabase (ownership-verified via `case_id` + `user_id`). The current `legal_notice_draft` is loaded from the case record. Supports answering clarifying questions, editing the notice draft, and requesting changes. User and assistant messages are persisted to Supabase automatically.

**Auth**: Bearer token required

**Request** — `ChatRequestDTO`

| Field | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | Yes | UUID of existing case |
| `message` | string | Yes | User's message |
| `history` | list\[ChatMessageDTO\] | No | Conversation history |
| `current_notice_draft` | string | No | Current notice to edit |

`ChatMessageDTO`:

| Field | Type | Description |
|---|---|---|
| `role` | string | `"user"` or `"assistant"` |
| `content` | string | Message body |

```json
{
  "case_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Please make the deadline 30 days instead of 15",
  "history": [
    {"role": "user", "content": "The landlord lives in Delhi"},
    {"role": "assistant", "content": "I've updated the address."}
  ],
  "current_notice_draft": "Existing notice text..."
}
```

**Response** — `ChatResponseDTO`

| Field | Type | Description |
|---|---|---|
| `reply` | string | AI reply message |
| `suggested_actions` | list\[ActionButton\] | Suggested next actions |
| `updated_sections` | list | Updated law sections |
| `updated_notice` | string | Updated notice draft (if edited) |
| `clarifying_questions` | list\[ClarifyingQuestion\] | Follow-up questions |

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"case_id":"...","message":"Make deadline 30 days","current_notice_draft":"..."}'
```

---

## Documents

### GET /documents/search

Search Indian law texts using hybrid RAG (vector similarity + BM25). No authentication required.

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | string | **required** | Search query (min 2 chars) |
| `top_k` | int | 5 | Results to return (1-20) |
| `acts` | string | null | Comma-separated act names to filter |
| `min_score` | float | 0.0 | Minimum relevance score (0.0-1.0) |
| `hybrid` | bool | true | Enable hybrid vector+BM25 search |
| `rerank` | bool | false | Enable cross-encoder reranking |
| `vector_weight` | float | 0.7 | Vector score weight in fusion (0.0-1.0) |

**Response** — `SearchResponseDTO`

| Field | Type | Description |
|---|---|---|
| `results` | list\[LawSearchResultDTO\] | Matching law sections |
| `query` | string | Original query |
| `total` | int | Number of results returned |

`LawSearchResultDTO`:

| Field | Type | Description |
|---|---|---|
| `act` | string | Act name (e.g. "Transfer of Property Act 1882") |
| `chapter` | string or null | Chapter name |
| `section_number` | string or null | Section number (e.g. "Section 106") |
| `section_title` | string or null | Section title |
| `score` | float | Fused relevance score |
| `excerpt` | string | First 300 chars of chunk text |

```bash
curl "http://localhost:8000/api/v1/documents/search?q=rent+deposit+refund&top_k=5&hybrid=true"
```

### GET /documents/health

Health check for the document search service.

```json
{
  "status": "ok"
}
```

---

## Voice

### POST /voice/transcribe

Transcribe an audio file to text using OpenAI Whisper (local model). Accepts WAV, WebM, MP3, M4A, and other formats supported by soundfile.

**Auth**: None

**Request**: multipart/form-data

| Field | Type | Required | Description |
|---|---|---|---|
| `audio_file` | UploadFile (audio) | Yes | Audio file (WAV, WebM, MP3, M4A) |
| `language` | string | No | Language hint (e.g. `"en"`, `"hi"`). Default: `"hi"` |

**Response** (200):

| Field | Type | Description |
|---|---|---|
| `transcript` | string | Transcribed text |
| `detected_language` | string | Language code |
| `confidence` | float | Confidence score |

```json
{
  "transcript": "मेरे मकान मालिक ने मेरी सिक्योरिटी डिपॉजिट वापस नहीं की",
  "detected_language": "hi",
  "confidence": 0.95
}
```

**Errors**:
- 400: Could not read audio file (unsupported format or corrupted file)

```bash
curl -X POST http://localhost:8000/api/v1/voice/transcribe \
  -F "audio_file=@recording.wav" \
  -F "language=en"
```

---

## Health

### GET /health

Simple health check.

```json
{
  "status": "ok",
  "service": "LexAgent API"
}
```

---

## DTO Reference

### Auth DTOs

**RegisterDTO**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `email` | EmailStr | Yes | Valid email |
| `password` | string | Yes | Min 8 characters |
| `full_name` | string | Yes | |
| `preferred_language` | `"en"` \| `"hi"` | No | Default: `"en"` |

**LoginDTO**

| Field | Type | Required |
|---|---|---|
| `email` | EmailStr | Yes |
| `password` | string | Yes |

**AuthResponseDTO**

| Field | Type |
|---|---|
| `email` | string |
| `full_name` | string |
| `access_token` | string |
| `token_type` | string |

**UserProfileDTO**

| Field | Type |
|---|---|
| `email` | string |
| `full_name` | string |
| `preferred_language` | LanguageEnum |
| `case_count` | int |

---

### Case DTOs

**Enums**

| Enum | Values |
|---|---|
| `CaseTypeEnum` | `tenancy_dispute`, `property_ownership`, `property_registration`, `other` |
| `SeverityEnum` | `low`, `medium`, `high`, `urgent` |
| `CaseStatusEnum` | `processing`, `analyzed`, `notice_generated`, `closed` |

**CreateCaseDTO**

| Field | Type | Required | Default |
|---|---|---|---|
| `description` | string | Yes | |
| `language` | string | No | `"en"` |

**LegalSectionDTO**

| Field | Type | Description |
|---|---|---|
| `act` | string | Act name |
| `section` | string | Section number/name |
| `title` | string | Section title |
| `excerpt` | string or null | Text excerpt |
| `relevance_score` | float | 0.0 to 1.0 |

**CaseResponseDTO**

| Field | Type |
|---|---|
| `case_id` | string |
| `status` | CaseStatusEnum |
| `case_type` | CaseTypeEnum or null |
| `severity` | SeverityEnum or null |
| `relevant_sections` | list\[LegalSectionDTO\] |
| `summary` | string or null |
| `next_steps` | list\[NextStep\] |
| `pdf_ready` | bool |
| `created_at` | datetime or null |
| `ai_message` | string or null |
| `clarifying_questions` | list\[ClarifyingQuestion\] |
| `action_buttons` | list\[ActionButton\] |

**CaseDetailDTO** (extends CaseResponseDTO)

| Field | Type |
|---|---|
| *inherits CaseResponseDTO* | |
| `description` | string |
| `agent_reasoning` | string or null |
| `legal_notice_draft` | string or null |
| `pdf_url` | string or null |

**CaseListResponseDTO**

| Field | Type |
|---|---|
| `cases` | list\[CaseResponseDTO\] |
| `total` | int |

---

### Agent DTOs

**PersonDetailsDTO**

| Field | Type |
|---|---|
| `name` | string |
| `address` | string |
| `phone` | string or null |
| `email` | string or null |

**ClarifyingQuestion**

| Field | Type |
|---|---|
| `question` | string |
| `key` | string |

**ActionButton**

| Field | Type | Default |
|---|---|---|
| `label` | string | |
| `message` | string | |
| `style` | string | `"default"` |

**NextStep**

| Field | Type |
|---|---|
| `number` | int |
| `text` | string |
| `action_label` | string |
| `action_message` | string |

**AnalyzeRequestDTO**

| Field | Type | Required |
|---|---|---|
| `case_id` | string | Yes |
| `description` | string | Yes |
| `user_name` | string | Yes |
| `opponent_name` | string | Yes |
| `opponent_address` | string | Yes |
| `language` | string | No |

**AnalyzeResponseDTO**

| Field | Type |
|---|---|
| `case_type` | string |
| `severity` | string |
| `relevant_sections` | list |
| `legal_notice_draft` | string |
| `summary` | string |
| `next_steps` | list\[NextStep\] |
| `reasoning_trace` | string |
| `clarifying_questions` | list\[ClarifyingQuestion\] |
| `action_buttons` | list\[ActionButton\] |
| `ai_message` | string |

**ChatMessageDTO**

| Field | Type |
|---|---|
| `role` | string |
| `content` | string |

**ChatRequestDTO**

| Field | Type | Required | Default |
|---|---|---|---|
| `case_id` | string | Yes | |
| `message` | string | Yes | |
| `history` | list\[ChatMessageDTO\] | No | `[]` |
| `current_notice_draft` | string | No | `""` |

**ChatResponseDTO**

| Field | Type |
|---|---|
| `reply` | string |
| `suggested_actions` | list\[ActionButton\] |
| `updated_sections` | list |
| `updated_notice` | string |
| `clarifying_questions` | list\[ClarifyingQuestion\] |

**GeneratePdfDTO**

| Field | Type |
|---|---|
| `case_id` | string |
| `notice_content` | string |
| `user_details` | PersonDetailsDTO |
| `recipient_details` | PersonDetailsDTO |

**PdfResponseDTO**

| Field | Type |
|---|---|
| `pdf_url` | string |
| `pdf_id` | string |
| `generated_at` | string |

---

### Document DTOs

**SearchRequestDTO**

| Field | Type | Default |
|---|---|---|
| `query` | string | |
| `top_k` | int | 5 |
| `acts` | list\[string\] or null | null |
| `min_score` | float | 0.0 |
| `use_hybrid` | bool | true |
| `use_rerank` | bool | false |
| `vector_weight` | float | 0.7 |

**LawSearchResultDTO**

| Field | Type |
|---|---|
| `act` | string |
| `chapter` | string or null |
| `section_number` | string or null |
| `section_title` | string or null |
| `score` | float |
| `excerpt` | string |

**SearchResponseDTO**

| Field | Type |
|---|---|
| `results` | list\[LawSearchResultDTO\] |
| `query` | string |
| `total` | int |

---

## Voice Response (no DTO — raw dict)

| Field | Type |
|---|---|
| `transcript` | string |
| `detected_language` | string |
| `confidence` | float |

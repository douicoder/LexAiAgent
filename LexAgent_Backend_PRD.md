# LexAgent — Backend PRD
**India's Autonomous Legal Aid Agent**
Version 1.0 | FAR AWAY Hackathon 2026 | Theme: Agentic & Autonomous Systems

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Folder Structure](#3-folder-structure)
4. [How the Agent Works](#4-how-the-agent-works)
5. [Database Models](#5-database-models)
6. [DTOs (Data Transfer Objects)](#6-dtos)
7. [Interfaces](#7-interfaces)
8. [Service Implementations](#8-service-implementations)
9. [API Endpoints](#9-api-endpoints)
10. [AutoMapper](#10-automapper)
11. [Helper Classes](#11-helper-classes)
12. [Config & Environment Variables](#12-config--environment-variables)
13. [main.py Entry Point](#13-mainpy-entry-point)
14. [RAG Ingestion Script](#14-rag-ingestion-script)
15. [Day-by-Day Build Plan](#15-day-by-day-build-plan)

---

## 1. Project Overview

LexAgent is an autonomous AI-powered legal aid system for India. A user describes their legal problem in Hindi or English — the system classifies it, searches actual Indian law documents (BNS 2023, CrPC, Consumer Protection Act, RTI Act), reasons about the relevant sections, drafts a legal notice, and generates a downloadable PDF — all autonomously.

### The Problem
80% of Indians cannot afford a lawyer for basic legal disputes. LexAgent gives everyone access to instant, accurate, law-grounded legal assistance for free.

### Core Flow
```
User Input (Hindi/English voice or text)
            ↓
    Whisper API (transcription if voice)
            ↓
    TextHelper (language detect + translate)
            ↓
    Agent Pipeline (GPT-4o via GitHub Models)
         ↓              ↓
  classify_case     search_law (RAG)
  tool call         → hits pgvector
         ↓              ↓
    Combine results + generate summary
            ↓
    Save to Supabase DB
            ↓
    PDF Generator (ReportLab)
            ↓
    Upload to Supabase Storage
            ↓
    Return public PDF URL to user
```

---

## 2. Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Framework | FastAPI (Python 3.11) | Async, fast, auto docs |
| LLM | GPT-4o via GitHub Models | Free quota, tool calling |
| Embeddings | text-embedding-3-small via GitHub Models | Free, great quality |
| RAG Framework | LlamaIndex | Best for document RAG |
| Vector DB | Supabase pgvector | Already in Supabase, no extra setup |
| Database | Supabase (PostgreSQL) | Auth + DB + Storage in one |
| PDF Generation | ReportLab | Professional legal formatting |
| Voice | Whisper API via GitHub Models | Hindi/English transcription |
| ORM | SQLAlchemy | Type-safe DB access |
| Validation | Pydantic v2 | DTO validation |
| Auth | JWT (python-jose) + bcrypt | Secure token auth |
| Frontend | Next.js 14 + Tailwind | (separate repo) |
| Deploy Backend | Railway | Free $5 credit |
| Deploy Frontend | Vercel | Free |

---

## 3. Folder Structure

```
lexagent/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry point
│   │   ├── config.py                # Settings, env vars
│   │   ├── database.py              # DB connection
│   │   │
│   │   ├── api/                     # Route handlers (thin layer, calls services)
│   │   │   ├── __init__.py
│   │   │   ├── auth.py              # /auth/register, /auth/login, /auth/me
│   │   │   ├── cases.py             # /cases CRUD
│   │   │   ├── agent.py             # /agent/analyze, /agent/chat, /agent/generate-pdf
│   │   │   ├── documents.py         # /documents/search
│   │   │   └── voice.py             # /voice/transcribe
│   │   │
│   │   ├── models/                  # SQLAlchemy DB models
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── case.py
│   │   │   └── document.py          # LawChunk with pgvector embedding
│   │   │
│   │   ├── dto/                     # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth_dto.py
│   │   │   ├── case_dto.py
│   │   │   ├── agent_dto.py
│   │   │   └── document_dto.py
│   │   │
│   │   ├── interfaces/              # Abstract base classes (contracts)
│   │   │   ├── __init__.py
│   │   │   ├── i_case_service.py
│   │   │   ├── i_agent_service.py
│   │   │   ├── i_rag_service.py
│   │   │   └── i_pdf_service.py
│   │   │
│   │   ├── services/                # Business logic (implements interfaces)
│   │   │   ├── __init__.py
│   │   │   ├── case_service.py
│   │   │   ├── agent_service.py     # THE BRAIN — multi-step tool calling agent
│   │   │   ├── rag_service.py       # LlamaIndex + pgvector
│   │   │   └── pdf_service.py       # ReportLab PDF generation
│   │   │
│   │   ├── mapper/
│   │   │   └── auto_mapper.py       # Model ↔ DTO conversion
│   │   │
│   │   └── helpers/
│   │       ├── auth_helper.py       # JWT, bcrypt
│   │       ├── text_helper.py       # Language detection, translation
│   │       ├── legal_helper.py      # System prompts, templates
│   │       └── pdf_helper.py        # ReportLab styles, layout
│   │
│   ├── scripts/
│   │   └── ingest_laws.py           # One-time script to embed law PDFs
│   │
│   ├── law_docs/                    # Raw law PDFs (not committed to git)
│   │   ├── BNS_2023.pdf
│   │   ├── CrPC.pdf
│   │   ├── Consumer_Protection_Act_2019.pdf
│   │   └── RTI_Act_2005.pdf
│   │
│   ├── requirements.txt
│   ├── .env
│   └── Dockerfile
│
└── frontend/                        # Next.js (separate)
```

---

## 4. How the Agent Works

This is the most important section. The agent is NOT just a single ChatGPT call. It is a **multi-step reasoning loop** using tool calling.

### What is Tool Calling?

Tool calling means the LLM can decide to call a function during its response, wait for the result, and then continue reasoning. The model says "I need to search the law database" — your code runs the search — the results go back to the model — the model continues.

### The Agent Loop (AgentService)

```
START: User description arrives
│
├─ Message 1 sent to GPT-4o with tools: [classify_case, search_law]
│
├─ GPT-4o responds: "I will call classify_case first"
│   └─ classify_case(description) → { case_type: "civil", severity: "medium" }
│
├─ Result sent back to GPT-4o
│
├─ GPT-4o responds: "Now I will search the law"
│   └─ search_law("security deposit landlord breach of trust")
│       → RAG hits pgvector
│       → returns [BNS 316, Consumer Protection Act S.35, ...]
│
├─ Results sent back to GPT-4o
│
├─ GPT-4o now has everything it needs
│   └─ Generates final JSON:
│       {
│         case_type, severity,
│         relevant_sections (from RAG),
│         summary (GPT writes this),
│         next_steps (GPT writes this),
│         legal_notice_draft (GPT writes this)
│       }
│
END: Results saved to DB, returned to user
```

### Why RAG for the sections?

Without RAG, GPT-4o would guess section numbers from memory — it might hallucinate "IPC 420" when the correct law is now "BNS 316" (India renamed IPC to BNS in 2023). With RAG, the actual law text is retrieved from your embedded PDFs and given to GPT-4o as context — so all citations are accurate and verifiable.

---

## 5. Database Models

### user.py

```python
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid, datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    preferred_language = Column(String, default="en")  # "en" | "hi"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.datetime.utcnow)
```

### case.py

```python
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid, datetime

class Case(Base):
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)              # original user input
    language = Column(String, default="en")
    case_type = Column(String)                              # civil/criminal/consumer/rti/labour
    severity = Column(String)                               # low/medium/high/urgent
    status = Column(String, default="processing")           # processing/analyzed/notice_generated/closed
    relevant_sections = Column(JSONB, default=list)         # list of {act, section, title, score}
    summary = Column(Text)                                  # GPT-generated summary
    next_steps = Column(JSONB, default=list)                # list of strings
    agent_reasoning = Column(Text)                          # full reasoning trace for transparency
    legal_notice_draft = Column(Text)                       # raw draft before PDF
    pdf_url = Column(String)                                # Supabase storage public URL
    pdf_id = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.datetime.utcnow)
```

### document.py

```python
from pgvector.sqlalchemy import Vector

class LawChunk(Base):
    """
    Each row is one chunk (~500 tokens) of a law document.
    The embedding column is a 1536-dim vector from text-embedding-3-small.
    pgvector does cosine similarity search on this column.
    """
    __tablename__ = "law_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    act_name = Column(String, nullable=False)     # "BNS 2023", "CrPC", "Consumer Protection Act 2019"
    section_number = Column(String)               # "316", "35", "6"
    section_title = Column(String)                # "Criminal breach of trust"
    chunk_text = Column(Text, nullable=False)     # raw text of this chunk
    embedding = Column(Vector(1536))              # pgvector column — DO NOT change dimension
    chunk_index = Column(String)                  # position within section for ordering
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
```

---

## 6. DTOs

### auth_dto.py

```python
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from enum import Enum

class LanguageEnum(str, Enum):
    EN = "en"
    HI = "hi"

class RegisterDTO(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    preferred_language: LanguageEnum = LanguageEnum.EN

    @field_validator("password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class LoginDTO(BaseModel):
    email: EmailStr
    password: str

class AuthResponseDTO(BaseModel):
    email: str
    full_name: str
    access_token: str
    token_type: str = "bearer"

class UserProfileDTO(BaseModel):
    email: str
    full_name: str
    preferred_language: LanguageEnum
    case_count: int
```

### case_dto.py

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class CaseTypeEnum(str, Enum):
    CIVIL = "civil"
    CRIMINAL = "criminal"
    CONSUMER = "consumer"
    RTI = "rti"
    LABOUR = "labour"

class SeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class CaseStatusEnum(str, Enum):
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    NOTICE_GENERATED = "notice_generated"
    CLOSED = "closed"

class LegalSectionDTO(BaseModel):
    act: str                  # "BNS 2023"
    section: str              # "316"
    title: str                # "Criminal breach of trust"
    excerpt: Optional[str]    # first 200 chars of the section text
    relevance_score: float    # 0.0 - 1.0 from vector similarity

class CreateCaseDTO(BaseModel):
    description: str
    language: str = "en"

class CaseResponseDTO(BaseModel):
    case_id: str
    status: CaseStatusEnum
    case_type: Optional[CaseTypeEnum]
    severity: Optional[SeverityEnum]
    relevant_sections: List[LegalSectionDTO] = []
    summary: Optional[str]
    next_steps: List[str] = []
    pdf_ready: bool = False
    created_at: Optional[datetime]

class CaseDetailDTO(CaseResponseDTO):
    description: str
    agent_reasoning: Optional[str]
    legal_notice_draft: Optional[str]
    pdf_url: Optional[str]

class CaseListResponseDTO(BaseModel):
    cases: List[CaseResponseDTO]
    total: int
```

### agent_dto.py

```python
from pydantic import BaseModel
from typing import List, Optional

class PersonDetailsDTO(BaseModel):
    name: str
    address: str
    phone: Optional[str] = None
    email: Optional[str] = None

class AnalyzeRequestDTO(BaseModel):
    case_id: str
    description: str
    user_name: str
    opponent_name: str
    opponent_address: str
    language: str = "en"

class AnalyzeResponseDTO(BaseModel):
    case_type: str
    severity: str
    relevant_sections: list
    legal_notice_draft: str
    summary: str
    next_steps: List[str]
    reasoning_trace: str          # full agent tool call log (for transparency)

class ChatMessageDTO(BaseModel):
    role: str                     # "user" | "assistant"
    content: str

class ChatRequestDTO(BaseModel):
    case_id: str
    message: str
    history: List[ChatMessageDTO] = []

class ChatResponseDTO(BaseModel):
    reply: str
    suggested_actions: List[str] = []
    updated_sections: list = []

class GeneratePdfDTO(BaseModel):
    case_id: str
    notice_content: str
    user_details: PersonDetailsDTO
    recipient_details: PersonDetailsDTO

class PdfResponseDTO(BaseModel):
    pdf_url: str
    pdf_id: str
    generated_at: str
```

### document_dto.py

```python
from pydantic import BaseModel
from typing import List, Optional

class SearchRequestDTO(BaseModel):
    query: str
    top_k: int = 5
    acts: Optional[List[str]] = None  # filter by specific acts

class LawSearchResultDTO(BaseModel):
    act: str
    section: str
    title: str
    excerpt: str
    relevance_score: float

class SearchResponseDTO(BaseModel):
    results: List[LawSearchResultDTO]
    query: str
    total: int
```

---

## 7. Interfaces

### i_rag_service.py

```python
from abc import ABC, abstractmethod
from typing import List, Optional

class IRagService(ABC):

    @abstractmethod
    async def search(self, query: str, top_k: int = 5, acts: Optional[List[str]] = None) -> List[dict]:
        """
        Semantic search over embedded law documents.
        Returns list of {act, section, title, excerpt, relevance_score}
        """
        ...

    @abstractmethod
    async def ingest_document(self, pdf_path: str, act_name: str) -> bool:
        """
        Chunk, embed, and store a law PDF into pgvector.
        Returns True on success.
        """
        ...
```

### i_agent_service.py

```python
from abc import ABC, abstractmethod
from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO, ChatRequestDTO, ChatResponseDTO

class IAgentService(ABC):

    @abstractmethod
    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        """
        Full multi-step agent pipeline:
        1. Detect language, translate if Hindi
        2. classify_case tool call → case_type + severity
        3. search_law tool call → RAG retrieves actual law sections
        4. Generate summary, next_steps, legal_notice_draft
        5. Return structured result
        """
        ...

    @abstractmethod
    async def chat(self, request: ChatRequestDTO) -> ChatResponseDTO:
        """
        Conversational follow-up about a case.
        Uses full conversation history + case context.
        """
        ...
```

### i_case_service.py

```python
from abc import ABC, abstractmethod
from typing import List
from app.dto.case_dto import CreateCaseDTO, CaseResponseDTO, CaseDetailDTO, CaseListResponseDTO

class ICaseService(ABC):

    @abstractmethod
    async def create_case(self, dto: CreateCaseDTO, user_id: str) -> CaseResponseDTO:
        """Create case, trigger agent pipeline, return initial response."""
        ...

    @abstractmethod
    async def get_case(self, case_id: str, user_id: str) -> CaseDetailDTO:
        """Get full case details. Raises 404 if not found or not owned by user."""
        ...

    @abstractmethod
    async def list_cases(self, user_id: str) -> CaseListResponseDTO:
        """List all cases for a user, newest first."""
        ...

    @abstractmethod
    async def delete_case(self, case_id: str, user_id: str) -> bool:
        """Soft delete a case. Raises 404 if not found or not owned by user."""
        ...
```

### i_pdf_service.py

```python
from abc import ABC, abstractmethod

class IPdfService(ABC):

    @abstractmethod
    async def generate_legal_notice(
        self,
        notice_content: str,
        user_details: dict,
        recipient_details: dict,
        sections: list,
        case_type: str
    ) -> bytes:
        """
        Generate a formatted legal notice PDF.
        Returns raw PDF bytes.
        """
        ...

    @abstractmethod
    async def upload_to_storage(self, pdf_bytes: bytes, filename: str) -> str:
        """
        Upload PDF bytes to Supabase storage bucket.
        Returns public URL string.
        """
        ...
```

---

## 8. Service Implementations

### rag_service.py

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.vector_stores.supabase import SupabaseVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from app.interfaces.i_rag_service import IRagService
from app.config import settings

class RagService(IRagService):
    def __init__(self):
        # Point to GitHub Models endpoint for embeddings (free)
        self.embed_model = OpenAIEmbedding(
            model="text-embedding-3-small",
            api_key=settings.GITHUB_TOKEN,
            api_base="https://models.inference.ai.azure.com"
        )
        Settings.embed_model = self.embed_model

        self.vector_store = SupabaseVectorStore(
            postgres_connection_string=settings.DATABASE_URL,
            collection_name="law_chunks"
        )
        self.index = VectorStoreIndex.from_vector_store(self.vector_store)

    async def search(self, query: str, top_k: int = 5, acts=None) -> list:
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        nodes = await retriever.aretrieve(query)

        results = []
        for node in nodes:
            meta = node.metadata
            # Filter by act if specified
            if acts and meta.get("act_name") not in acts:
                continue
            results.append({
                "act": meta.get("act_name"),
                "section": meta.get("section_number"),
                "title": meta.get("section_title"),
                "excerpt": node.text[:300],
                "relevance_score": round(node.score, 3)
            })
        return results

    async def ingest_document(self, pdf_path: str, act_name: str) -> bool:
        docs = SimpleDirectoryReader(input_files=[pdf_path]).load_data()
        for doc in docs:
            doc.metadata["act_name"] = act_name
        VectorStoreIndex.from_documents(
            docs,
            vector_store=self.vector_store,
        )
        return True
```

### agent_service.py

```python
from openai import AsyncOpenAI
from app.interfaces.i_agent_service import IAgentService
from app.interfaces.i_rag_service import IRagService
from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO, ChatRequestDTO, ChatResponseDTO
from app.helpers.legal_helper import LegalHelper
from app.helpers.text_helper import TextHelper
from app.config import settings
import json

# Tool definitions — GPT-4o decides when to call these
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "classify_case",
            "description": "Classify the legal case type and urgency severity based on the description",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_type": {
                        "type": "string",
                        "enum": ["civil", "criminal", "consumer", "rti", "labour"],
                        "description": "The category of legal dispute"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "How urgently the person needs help"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why you chose this classification"
                    }
                },
                "required": ["case_type", "severity", "reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_law",
            "description": "Search the Indian law database (BNS 2023, CrPC, Consumer Protection Act, RTI Act) for relevant sections",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The legal concept to search for"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of results to retrieve"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

class AgentService(IAgentService):
    def __init__(self, rag: IRagService):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.inference.ai.azure.com"
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def analyze_case(self, req: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        # Step 1: Translate if Hindi
        description = req.description
        if req.language == "hi":
            description = await self.text.translate_to_english(description)

        messages = [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": f"""
Analyze this legal problem and help the person:

Problem: {description}

Person's name: {req.user_name}
Opponent's name: {req.opponent_name}

Steps:
1. First classify the case type and severity
2. Then search for relevant law sections
3. Finally generate a complete legal notice draft
"""}
        ]

        reasoning_trace = []
        classification = {}
        law_sections = []

        # Step 2: Agent loop — runs until model stops calling tools
        while True:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                response_format={"type": "text"}
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append(msg)  # add assistant message with tool_calls

                for tool_call in msg.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    tool_name = tool_call.function.name

                    if tool_name == "classify_case":
                        result = args
                        classification = args
                        reasoning_trace.append(f"[classify_case] → {args}")

                    elif tool_name == "search_law":
                        result = await self.rag.search(
                            query=args["query"],
                            top_k=args.get("top_k", 5)
                        )
                        law_sections.extend(result)
                        reasoning_trace.append(f"[search_law: '{args['query']}'] → {len(result)} results")

                    # Feed tool result back to model
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
            else:
                # Model finished — parse final JSON response
                break

        # Step 3: Ask model to generate final structured output
        messages.append({
            "role": "user",
            "content": f"""
Now generate the final output as JSON with these exact keys:
{{
  "summary": "2-3 sentence plain language summary of the case",
  "next_steps": ["list", "of", "3-5", "actionable", "steps"],
  "legal_notice_draft": "Full formal legal notice text with proper legal language, citing the sections found"
}}

Available law sections from the database:
{json.dumps(law_sections, indent=2)}

Opponent details for the notice:
Name: {req.opponent_name}
Address: {req.opponent_address}

Return ONLY valid JSON. No markdown backticks.
"""
        })

        final_response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )

        final_text = final_response.choices[0].message.content
        final_data = json.loads(final_text.strip())

        return AnalyzeResponseDTO(
            case_type=classification.get("case_type", "civil"),
            severity=classification.get("severity", "medium"),
            relevant_sections=law_sections,
            legal_notice_draft=final_data["legal_notice_draft"],
            summary=final_data["summary"],
            next_steps=final_data["next_steps"],
            reasoning_trace="\n".join(reasoning_trace)
        )

    async def chat(self, req: ChatRequestDTO) -> ChatResponseDTO:
        messages = [
            {"role": "system", "content": self.legal.system_prompt()},
        ]
        for h in req.history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": req.message})

        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        reply_text = response.choices[0].message.content or ""
        return ChatResponseDTO(reply=reply_text)
```

### case_service.py

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.interfaces.i_case_service import ICaseService
from app.interfaces.i_agent_service import IAgentService
from app.models.case import Case
from app.dto.case_dto import CreateCaseDTO, CaseResponseDTO, CaseDetailDTO, CaseListResponseDTO
from app.dto.agent_dto import AnalyzeRequestDTO
from app.mapper.auto_mapper import AutoMapper
from app.helpers.text_helper import TextHelper
import uuid

class CaseService(ICaseService):
    def __init__(self, db: AsyncSession, agent: IAgentService):
        self.db = db
        self.agent = agent
        self.text = TextHelper()

    async def create_case(self, dto: CreateCaseDTO, user_id: str) -> CaseResponseDTO:
        # Create case record immediately with processing status
        case = Case(
            id=uuid.uuid4(),
            user_id=user_id,
            description=dto.description,
            language=dto.language,
            status="processing"
        )
        self.db.add(case)
        await self.db.commit()

        # Run agent pipeline (in production this would be a background task)
        analyze_req = AnalyzeRequestDTO(
            case_id=str(case.id),
            description=dto.description,
            user_name="",       # filled in later during PDF generation
            opponent_name="",
            opponent_address="",
            language=dto.language
        )
        result = await self.agent.analyze_case(analyze_req)

        # Update case with agent results
        case.case_type = result.case_type
        case.severity = result.severity
        case.status = "analyzed"
        case.relevant_sections = result.relevant_sections
        case.summary = result.summary
        case.next_steps = result.next_steps
        case.agent_reasoning = result.reasoning_trace
        case.legal_notice_draft = result.legal_notice_draft
        await self.db.commit()
        await self.db.refresh(case)

        return AutoMapper.case_to_response_dto(case)

    async def get_case(self, case_id: str, user_id: str) -> CaseDetailDTO:
        result = await self.db.execute(
            select(Case).where(Case.id == case_id, Case.user_id == user_id)
        )
        case = result.scalar_one_or_none()
        if not case:
            raise ValueError("Case not found")
        return AutoMapper.case_to_detail_dto(case)

    async def list_cases(self, user_id: str) -> CaseListResponseDTO:
        result = await self.db.execute(
            select(Case).where(Case.user_id == user_id).order_by(Case.created_at.desc())
        )
        cases = result.scalars().all()
        return CaseListResponseDTO(
            cases=AutoMapper.case_list_to_dto(cases),
            total=len(cases)
        )

    async def delete_case(self, case_id: str, user_id: str) -> bool:
        result = await self.db.execute(
            select(Case).where(Case.id == case_id, Case.user_id == user_id)
        )
        case = result.scalar_one_or_none()
        if not case:
            raise ValueError("Case not found")
        await self.db.delete(case)
        await self.db.commit()
        return True
```

### pdf_service.py

```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib import colors
from app.interfaces.i_pdf_service import IPdfService
from app.helpers.pdf_helper import PdfHelper
from supabase import create_client
from app.config import settings
import io, uuid, datetime

class PdfService(IPdfService):
    def __init__(self):
        self.supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.helper = PdfHelper()

    async def generate_legal_notice(self, notice_content, user_details, recipient_details, sections, case_type) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2.5*cm,
            leftMargin=2.5*cm,
            topMargin=2.5*cm,
            bottomMargin=2.5*cm
        )
        styles = self.helper.get_styles()
        story = []

        # Header
        story.append(Paragraph("LEGAL NOTICE", styles["NoticeTitle"]))
        story.append(Spacer(1, 0.3*cm))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.black))
        story.append(Spacer(1, 0.5*cm))

        # Date and From/To
        story.append(Paragraph(f"Date: {datetime.date.today().strftime('%d %B %Y')}", styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"<b>FROM:</b> {user_details['name']}", styles["Normal"]))
        story.append(Paragraph(user_details.get('address', ''), styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"<b>TO:</b> {recipient_details['name']}", styles["Normal"]))
        story.append(Paragraph(recipient_details.get('address', ''), styles["Normal"]))
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Spacer(1, 0.5*cm))

        # Body
        for para in notice_content.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), styles["Body"]))
                story.append(Spacer(1, 0.3*cm))

        # Relevant Sections
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("Relevant Legal Provisions:", styles["SectionTitle"]))
        for sec in sections:
            story.append(Paragraph(
                f"• {sec.get('act')} — Section {sec.get('section')}: {sec.get('title')}",
                styles["SectionItem"]
            ))

        # Signature
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(f"Yours faithfully,", styles["Normal"]))
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(f"<b>{user_details['name']}</b>", styles["Normal"]))

        # Footer note
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Paragraph(
            "Generated by LexAgent — AI-powered legal aid for India. This notice is for informational purposes.",
            styles["Footer"]
        ))

        doc.build(story)
        return buffer.getvalue()

    async def upload_to_storage(self, pdf_bytes: bytes, filename: str) -> str:
        file_path = f"notices/{filename}"
        self.supabase.storage.from_("legal-notices").upload(
            path=file_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf"}
        )
        url = self.supabase.storage.from_("legal-notices").get_public_url(file_path)
        return url
```

---

## 9. API Endpoints

Base URL: `http://localhost:8000/api/v1`

All protected endpoints require: `Authorization: Bearer <supabase_access_token>`

Important auth rule: Supabase user ids are backend-only. Never include the user id in `AuthResponseDTO`, `UserProfileDTO`, or any frontend-facing response. When a service needs the user id for database ownership fields such as `cases.user_id`, it must depend on `AuthHelper.get_current_user_id(...)` instead of accepting the id from the frontend.

### Auth Routes — auth.py

```python
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from app.dto.auth_dto import RegisterDTO, LoginDTO, AuthResponseDTO, UserProfileDTO
from app.helpers.auth_helper import AuthHelper, security

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=AuthResponseDTO, status_code=201)
async def register(dto: RegisterDTO):
    payload = await AuthHelper.supabase_sign_up(
        email=str(dto.email),
        password=dto.password,
        full_name=dto.full_name,
        preferred_language=dto.preferred_language.value,
    )
    return AuthResponseDTO(**AuthHelper.supabase_auth_response(payload))

@router.post("/login", response_model=AuthResponseDTO)
async def login(dto: LoginDTO):
    payload = await AuthHelper.supabase_sign_in(email=str(dto.email), password=dto.password)
    return AuthResponseDTO(**AuthHelper.supabase_auth_response(payload))

@router.get("/me", response_model=UserProfileDTO)
async def me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    user = await AuthHelper.get_current_supabase_user(credentials)
    return UserProfileDTO(**AuthHelper.supabase_profile_response(user))
```

### Cases Routes — cases.py

```python
router = APIRouter(prefix="/cases", tags=["cases"])

# POST /cases — create case + trigger agent
@router.post("", response_model=CaseResponseDTO, status_code=201)
async def create_case(dto: CreateCaseDTO, ...)

# GET /cases — list user's cases
@router.get("", response_model=CaseListResponseDTO)
async def list_cases(...)

# GET /cases/{case_id} — get full case detail
@router.get("/{case_id}", response_model=CaseDetailDTO)
async def get_case(case_id: str, ...)

# DELETE /cases/{case_id}
@router.delete("/{case_id}")
async def delete_case(case_id: str, ...)
```

### Agent Routes — agent.py

```python
router = APIRouter(prefix="/agent", tags=["agent"])

# POST /agent/analyze — full agent pipeline
@router.post("/analyze", response_model=AnalyzeResponseDTO)
async def analyze(dto: AnalyzeRequestDTO, ...)

# POST /agent/chat — follow-up conversation
@router.post("/chat", response_model=ChatResponseDTO)
async def chat(dto: ChatRequestDTO, ...)

# POST /agent/generate-pdf — generate + upload PDF
@router.post("/generate-pdf", response_model=PdfResponseDTO)
async def generate_pdf(dto: GeneratePdfDTO, ...)
```

### Voice & Document Routes

```python
# POST /voice/transcribe — multipart audio → text
@router.post("/voice/transcribe")
async def transcribe(audio_file: UploadFile, language: str = "hi")

# GET /documents/search?q=query&top_k=5&acts=BNS,Consumer
@router.get("/documents/search", response_model=SearchResponseDTO)
async def search_documents(q: str, top_k: int = 5, acts: Optional[str] = None)
```

---

## 10. AutoMapper

```python
from app.models.user import User
from app.models.case import Case
from app.dto.auth_dto import AuthResponseDTO, UserProfileDTO
from app.dto.case_dto import CaseResponseDTO, CaseDetailDTO, CaseListResponseDTO

class AutoMapper:
    """
    Converts DB models to DTOs.
    No SQLAlchemy model should ever reach the API layer directly.
    """

    @staticmethod
    def user_to_profile_dto(user: User, case_count: int = 0) -> UserProfileDTO:
        return UserProfileDTO(
            email=user.email,
            full_name=user.full_name,
            preferred_language=user.preferred_language,
            case_count=case_count
        )

    @staticmethod
    def user_to_auth_response(user: User, token: str) -> AuthResponseDTO:
        return AuthResponseDTO(
            email=user.email,
            full_name=user.full_name,
            access_token=token,
            token_type="bearer"
        )

    @staticmethod
    def case_to_response_dto(case: Case) -> CaseResponseDTO:
        return CaseResponseDTO(
            case_id=str(case.id),
            status=case.status,
            case_type=case.case_type,
            severity=case.severity,
            relevant_sections=case.relevant_sections or [],
            summary=case.summary,
            next_steps=case.next_steps or [],
            pdf_ready=bool(case.pdf_url),
            created_at=case.created_at
        )

    @staticmethod
    def case_to_detail_dto(case: Case) -> CaseDetailDTO:
        base = AutoMapper.case_to_response_dto(case)
        return CaseDetailDTO(
            **base.model_dump(),
            description=case.description,
            agent_reasoning=case.agent_reasoning,
            legal_notice_draft=case.legal_notice_draft,
            pdf_url=case.pdf_url
        )

    @staticmethod
    def case_list_to_dto(cases: list) -> list:
        return [AutoMapper.case_to_response_dto(c) for c in cases]
```

---

## 11. Helper Classes

### auth_helper.py

```python
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

security = HTTPBearer()

class AuthHelper:

    @staticmethod
    def _supabase_auth_url(path: str) -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/{path.lstrip('/')}"

    @staticmethod
    def _supabase_headers(token: str | None = None) -> dict[str, str]:
        bearer = token or settings.SUPABASE_KEY
        return {
            "apikey": settings.SUPABASE_KEY,
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }

    @staticmethod
    async def supabase_sign_up(email: str, password: str, full_name: str, preferred_language: str) -> dict:
        payload = {
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name,
                "preferred_language": preferred_language,
            },
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                AuthHelper._supabase_auth_url("signup"),
                headers=AuthHelper._supabase_headers(),
                json=payload,
            )
        if response.status_code >= 400:
            raise HTTPException(response.status_code, "Unable to register user")
        return response.json()

    @staticmethod
    async def supabase_sign_in(email: str, password: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                AuthHelper._supabase_auth_url("token?grant_type=password"),
                headers=AuthHelper._supabase_headers(),
                json={"email": email, "password": password},
            )
        if response.status_code >= 400:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        return response.json()

    @staticmethod
    async def supabase_get_user(access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                AuthHelper._supabase_auth_url("user"),
                headers=AuthHelper._supabase_headers(access_token),
            )
        if response.status_code >= 400:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
        return response.json()

    @staticmethod
    def supabase_auth_response(payload: dict) -> dict:
        user = payload.get("user") or payload
        session = payload.get("session") or payload
        metadata = user.get("user_metadata") or {}
        return {
            "email": user.get("email"),
            "full_name": metadata.get("full_name") or "",
            "access_token": session.get("access_token"),
            "token_type": "bearer",
        }

    @staticmethod
    def supabase_profile_response(user: dict) -> dict:
        metadata = user.get("user_metadata") or {}
        return {
            "email": user.get("email"),
            "full_name": metadata.get("full_name") or "",
            "preferred_language": metadata.get("preferred_language") or "en",
            "case_count": 0,
        }

    @staticmethod
    async def get_current_supabase_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> dict:
        return await AuthHelper.supabase_get_user(credentials.credentials)

    @staticmethod
    async def get_current_user_id(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> str:
        """
        Backend-only helper for services that need ownership keys.
        Do not return this value in API responses.
        """
        user = await AuthHelper.get_current_supabase_user(credentials)
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid user token")
        return user_id
```

Usage inside protected services/routes:

```python
@router.post("/cases", response_model=CaseResponseDTO)
async def create_case(
    dto: CreateCaseDTO,
    user_id: str = Depends(AuthHelper.get_current_user_id),
):
    # user_id is available for database writes, but is never exposed to frontend responses.
    ...
```

### text_helper.py

```python
from openai import AsyncOpenAI
from app.config import settings

class TextHelper:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.inference.ai.azure.com"
        )

    async def detect_language(self, text: str) -> str:
        """Returns 'hi' for Hindi, 'en' for English."""
        # Simple heuristic: check for Devanagari Unicode range
        devanagari = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        return "hi" if devanagari > len(text) * 0.1 else "en"

    async def translate_to_english(self, text: str) -> str:
        """Translate Hindi text to English using GPT-4o."""
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Translate the following Hindi text to English. Return only the translation."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content.strip()

    def clean_text(self, text: str) -> str:
        """Remove extra whitespace and normalize."""
        return " ".join(text.split())

    def truncate_safe(self, text: str, max_len: int = 2000) -> str:
        return text[:max_len] + "..." if len(text) > max_len else text
```

### legal_helper.py

```python
from datetime import date, timedelta

class LegalHelper:

    def system_prompt(self) -> str:
        return """You are LexAgent, an expert Indian legal assistant.

Your role is to help ordinary Indians understand their legal rights and take action.

Rules:
- Always cite specific sections from Indian law (BNS 2023, CrPC, Consumer Protection Act, RTI Act)
- Use clear, simple language in your explanations
- Be empathetic — users are often in stressful situations
- Legal notices must be formal, professional, and properly structured
- Always recommend consulting a qualified lawyer for court proceedings
- Base all section citations ONLY on what the search_law tool returns — never hallucinate sections

When writing legal notices:
- Use formal legal language
- Include the specific law sections found
- Give a 15-30 day response deadline
- State clearly what action is required"""

    def notice_template(self, case_type: str) -> str:
        templates = {
            "civil": "UNDER THE PROVISIONS OF THE BHARATIYA NYAYA SANHITA 2023",
            "consumer": "UNDER THE CONSUMER PROTECTION ACT 2019",
            "rti": "UNDER THE RIGHT TO INFORMATION ACT 2005",
            "labour": "UNDER THE LABOUR LAWS OF INDIA"
        }
        return templates.get(case_type, "UNDER THE APPLICABLE LAWS OF INDIA")

    def get_response_deadline(self, severity: str) -> int:
        """Returns deadline in days based on severity."""
        deadlines = {
            "urgent": 7,
            "high": 15,
            "medium": 30,
            "low": 60
        }
        return deadlines.get(severity, 30)
```

### pdf_helper.py

```python
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.lib.units import cm
import datetime

class PdfHelper:

    def get_styles(self):
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="NoticeTitle",
            fontSize=18,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
            spaceAfter=12
        ))
        styles.add(ParagraphStyle(
            name="SectionTitle",
            fontSize=12,
            fontName="Helvetica-Bold",
            spaceBefore=12,
            spaceAfter=6
        ))
        styles.add(ParagraphStyle(
            name="Body",
            fontSize=11,
            fontName="Helvetica",
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=8
        ))
        styles.add(ParagraphStyle(
            name="SectionItem",
            fontSize=10,
            fontName="Helvetica",
            leftIndent=20,
            spaceAfter=4
        ))
        styles.add(ParagraphStyle(
            name="Footer",
            fontSize=8,
            fontName="Helvetica",
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceBefore=12
        ))
        return styles

    def format_date_legal(self, dt=None) -> str:
        if dt is None:
            dt = datetime.date.today()
        return dt.strftime("%d %B %Y")
```

---

## 12. Config & Environment Variables

### config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # GitHub Models (free LLM + embeddings)
    GITHUB_TOKEN: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Database
    # Do not use Supabase DB URL. Use a normal app database URL.
    DATABASE_URL: str = "sqlite+aiosqlite:///./lexagent.db"

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

settings = Settings()
```

### .env (template)

```
GITHUB_TOKEN=github_pat_xxxxxxxxxxxx
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DATABASE_URL=sqlite+aiosqlite:///./lexagent.db
JWT_SECRET=your-super-secret-key-change-in-production
```

---

## 13. main.py Entry Point

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, cases, agent, documents, voice
from app.config import settings
from app.database import create_tables

app = FastAPI(
    title="LexAgent API",
    description="Autonomous Legal Aid Agent for India",
    version="1.0.0"
)

# CORS — allow Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Register routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(voice.router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    await create_tables()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "LexAgent API"}
```

---

## 14. RAG Ingestion Script

Run this ONCE before the hackathon demo to embed all law PDFs.

```python
# scripts/ingest_laws.py
import asyncio
from app.services.rag_service import RagService

LAW_DOCS = [
    ("law_docs/BNS_2023.pdf", "BNS 2023"),
    ("law_docs/CrPC.pdf", "CrPC"),
    ("law_docs/Consumer_Protection_Act_2019.pdf", "Consumer Protection Act 2019"),
    ("law_docs/RTI_Act_2005.pdf", "RTI Act 2005"),
]

async def main():
    rag = RagService()
    for pdf_path, act_name in LAW_DOCS:
        print(f"Ingesting {act_name}...")
        success = await rag.ingest_document(pdf_path, act_name)
        print(f"  {'Done' if success else 'Failed'}")
    print("All documents ingested!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 15. Day-by-Day Build Plan

### Day 1 — Foundation
- [x] Set up FastAPI project structure
- [x] Configure Supabase (enable pgvector extension: `create extension vector`)
- [x] Set up SQLAlchemy async with Supabase
- [x] Implement auth endpoints (register, login, me)
- [x] Test auth flow with Postman/curl

**End goal:** User can register, log in, get JWT, hit /me

### Day 2 — RAG Pipeline
- [x] Download law PDFs (BNS, CrPC, Consumer Protection Act, RTI Act)
- [ ] Set up LlamaIndex with Supabase pgvector
- [ ] Run `ingest_laws.py` — embed all 4 documents
- [ ] Test `/documents/search?q=landlord deposit` returns real law sections
- [ ] Verify relevance scores are meaningful

**End goal:** Semantic search returns accurate law citations

### Day 3 — Agent Brain
- [ ] Implement `AgentService` with tool calling loop
- [ ] Wire `search_law` tool to `RagService`
- [ ] Implement `classify_case` tool
- [ ] Test full analyze pipeline: description → classification + sections + draft
- [ ] Implement `CaseService` — create case + trigger agent + save results

**End goal:** POST /cases returns fully analyzed case with law sections

### Day 4 — PDF + Voice
- [ ] Implement `PdfService` with ReportLab
- [ ] Design legal notice template (header, body, sections, signature)
- [ ] Upload PDF to Supabase Storage
- [ ] Implement voice transcription endpoint (Whisper via GitHub Models)
- [ ] Test end-to-end: voice → text → analyze → PDF download

**End goal:** Full pipeline working from voice input to PDF output

### Day 5 — Polish + Chat
- [ ] Implement `/agent/chat` for follow-up questions
- [ ] Add proper error handling (404, 401, 422, 500)
- [ ] Add input validation edge cases
- [ ] Test all endpoints with Postman
- [ ] Write README with setup instructions

**End goal:** All endpoints working, clean error messages

### Day 6 — Deploy + Demo Prep
- [ ] Deploy backend to Railway
- [ ] Set all environment variables in Railway dashboard
- [ ] Test live URL
- [ ] Prepare 3 demo scenarios (deposit, consumer complaint, RTI)
- [ ] Record backup demo video
- [ ] Clean up GitHub repo, write good commit messages

**End goal:** Live URL, clean GitHub, demo rehearsed

---

## Requirements.txt

```
fastapi==0.111.0
uvicorn==0.30.1
sqlalchemy==2.0.30
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.7.1
pydantic-settings==2.3.0
pydantic[email]==2.7.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
openai==1.35.7
llama-index==0.10.43
llama-index-vector-stores-supabase==0.1.3
llama-index-embeddings-openai==0.1.10
pgvector==0.3.1
reportlab==4.2.0
supabase==2.5.0
httpx==0.27.0
python-dotenv==1.0.1
```

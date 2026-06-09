from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class CaseTypeEnum(str, Enum):
    TENANCY_DISPUTE       = "tenancy_dispute"
    PROPERTY_OWNERSHIP    = "property_ownership"
    PROPERTY_REGISTRATION = "property_registration"
    OTHER                 = "other"


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
    act: str
    section: str
    title: str
    excerpt: str | None = None
    relevance_score: float


class CreateCaseDTO(BaseModel):
    description: str
    language: str = "en"


class CaseResponseDTO(BaseModel):
    case_id: str
    status: CaseStatusEnum
    case_type: CaseTypeEnum | None = None
    severity: SeverityEnum | None = None
    relevant_sections: list[LegalSectionDTO] = []
    summary: str | None = None
    next_steps: list[str] = []
    pdf_ready: bool = False
    created_at: datetime | None = None


class CaseDetailDTO(CaseResponseDTO):
    description: str
    agent_reasoning: str | None = None
    legal_notice_draft: str | None = None
    pdf_url: str | None = None


class CaseListResponseDTO(BaseModel):
    cases: list[CaseResponseDTO]
    total: int

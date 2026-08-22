from pydantic import BaseModel


class DocumentDTO(BaseModel):
    id: str
    case_id: str
    doc_type: str
    title: str
    content: str
    status: str = "draft"
    created_at: str = ""
    updated_at: str | None = None


class ClarifyingQuestion(BaseModel):
    question: str
    key: str


class ActionButton(BaseModel):
    label: str
    message: str
    style: str = "default"


class NextStep(BaseModel):
    number: int
    text: str
    action_label: str = ""
    action_message: str = ""


class ActionStep(BaseModel):
    number: int
    text: str
    action_type: str = ""
    action_config: dict = {}
    status: str = "pending"


class LegalOptionDTO(BaseModel):
    id: str
    name: str
    forum: str
    tagline: str = ""
    recommended: bool = False
    cost_range: str = ""
    time_range: str = ""
    effort: str = ""  # Low | Medium | High
    success_likelihood: int = 0  # 0-100
    risk_level: str = "medium"
    pros: list[str] = []
    cons: list[str] = []
    evidence_required: list[str] = []
    best_for: str = ""  # cost | time | success | risk | control
    interoperability_note: str = ""
    next_steps: list[str] = []
    applicable_documents: list[str] = []


class PersonDetailsDTO(BaseModel):
    name: str
    address: str
    phone: str | None = None
    email: str | None = None


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
    legal_domain: str = ""
    relevant_sections: list
    legal_notice_draft: str = ""
    other_documents: list[DocumentDTO] = []
    summary: str
    next_steps: list[ActionStep] = []
    reasoning_trace: str
    clarifying_questions: list[ClarifyingQuestion] = []
    action_buttons: list[ActionButton] = []
    ai_message: str = ""
    case_readiness_score: int = 0
    evidence_available: list[str] = []
    evidence_missing: list[str] = []
    evidence_suggestions: list[str] = []
    risk_level: str = "medium"
    recommended_actions: list[str] = []
    is_sufficient: bool = True
    law_docs_available: list[str] = []
    law_docs_coverage: str = ""
    legal_options: list[LegalOptionDTO] = []
    option_comparison_note: str = ""


class ChatMessageDTO(BaseModel):
    role: str
    content: str


class ChatRequestDTO(BaseModel):
    case_id: str
    message: str
    history: list[ChatMessageDTO] = []
    current_notice_draft: str = ""


class ChatResponseDTO(BaseModel):
    reply: str
    suggested_actions: list[ActionButton] = []
    updated_sections: list = []
    updated_notice: str = ""
    clarifying_questions: list[ClarifyingQuestion] = []
    document: dict | None = None
    steps: list[ActionStep] | None = None


class GeneratePdfDTO(BaseModel):
    case_id: str
    notice_content: str
    user_details: PersonDetailsDTO
    recipient_details: PersonDetailsDTO


class PdfResponseDTO(BaseModel):
    pdf_url: str
    pdf_id: str
    generated_at: str


class ExecuteActionRequest(BaseModel):
    case_id: str
    step_number: int
    collected_info: dict = {}
    message: str = ""


class ExecuteActionResponse(BaseModel):
    reply: str
    document: DocumentDTO | None = None
    clarifying_questions: list[ClarifyingQuestion] = []
    action_buttons: list[ActionButton] = []
    missing_fields: list[str] = []
    done: bool = False

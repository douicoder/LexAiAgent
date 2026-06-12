from pydantic import BaseModel


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
    relevant_sections: list
    legal_notice_draft: str = ""
    summary: str
    next_steps: list[ActionStep] = []
    reasoning_trace: str
    clarifying_questions: list[ClarifyingQuestion] = []
    action_buttons: list[ActionButton] = []
    ai_message: str = ""


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


class DocumentDTO(BaseModel):
    id: str
    case_id: str
    doc_type: str
    title: str
    content: str
    status: str = "draft"
    created_at: str = ""
    updated_at: str | None = None


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

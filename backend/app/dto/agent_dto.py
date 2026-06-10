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
    legal_notice_draft: str
    summary: str
    next_steps: list[NextStep] = []
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


class GeneratePdfDTO(BaseModel):
    case_id: str
    notice_content: str
    user_details: PersonDetailsDTO
    recipient_details: PersonDetailsDTO


class PdfResponseDTO(BaseModel):
    pdf_url: str
    pdf_id: str
    generated_at: str

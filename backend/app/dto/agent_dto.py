from pydantic import BaseModel


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
    next_steps: list[str]
    reasoning_trace: str


class ChatMessageDTO(BaseModel):
    role: str
    content: str


class ChatRequestDTO(BaseModel):
    case_id: str
    message: str
    history: list[ChatMessageDTO] = []


class ChatResponseDTO(BaseModel):
    reply: str
    suggested_actions: list[str] = []
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

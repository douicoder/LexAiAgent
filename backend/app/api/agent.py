from fastapi import APIRouter, Depends

from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO, ChatMessageDTO, ChatRequestDTO, ChatResponseDTO
from app.helpers.auth_helper import AuthHelper
from app.services.agent_service import AgentService
from app.services.case_message_service import CaseMessageService
from app.services.rag_service import RagService
from app.services.supabase_db import SupabaseService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/analyze", response_model=AnalyzeResponseDTO)
async def analyze(
    dto: AnalyzeRequestDTO,
    user_id: str = Depends(AuthHelper.get_current_user_id),
) -> AnalyzeResponseDTO:
    rag = RagService()
    agent = AgentService(rag)
    return await agent.analyze_case(dto)


@router.post("/chat", response_model=ChatResponseDTO)
async def chat(
    dto: ChatRequestDTO,
    user_id: str = Depends(AuthHelper.get_current_user_id),
) -> ChatResponseDTO:
    supabase = SupabaseService()
    msg_service = CaseMessageService(supabase)

    # 1. Load full conversation history from DB (ownership-verified)
    db_messages = msg_service.get_messages(dto.case_id, user_id)
    dto.history = [
        ChatMessageDTO(role=m["role"], content=m["content"])
        for m in db_messages
    ]

    # 2. Load latest notice draft from case record
    case = supabase.get_case(dto.case_id, user_id)
    dto.current_notice_draft = case.get("legal_notice_draft", "") if case else ""

    # 3. Save new user message
    msg_service.add_message(dto.case_id, "user", dto.message)

    # 4. Call LLM with server-side data (history + notice draft)
    rag = RagService()
    agent = AgentService(rag)
    result = await agent.chat(dto)

    # 5. Save assistant response
    msg_service.add_message(dto.case_id, "assistant", result.reply)

    return result

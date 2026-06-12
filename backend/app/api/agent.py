from fastapi import APIRouter, Depends

from app.dto.agent_dto import (
    AnalyzeRequestDTO,
    AnalyzeResponseDTO,
    ChatMessageDTO,
    ChatRequestDTO,
    ChatResponseDTO,
    ExecuteActionRequest,
    ExecuteActionResponse,
)
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

    db_messages = msg_service.get_messages(dto.case_id, user_id)
    dto.history = [
        ChatMessageDTO(role=m["role"], content=m["content"])
        for m in db_messages
    ]

    case = supabase.get_case(dto.case_id, user_id)
    dto.current_notice_draft = case.get("legal_notice_draft", "") if case else ""

    msg_service.add_message(dto.case_id, "user", dto.message)

    rag = RagService()
    agent = AgentService(rag)
    result = await agent.chat(dto)

    msg_service.add_message(dto.case_id, "assistant", result.reply)

    if result.updated_notice:
        supabase.update_case(dto.case_id, {
            "legal_notice_draft": result.updated_notice,
        })

    if result.document and result.document.content:
        supabase.create_document({
            "id": result.document.id,
            "case_id": dto.case_id,
            "doc_type": result.document.doc_type,
            "title": result.document.title,
            "content": result.document.content,
            "status": "draft",
        })
    elif result.updated_notice:
        supabase.create_document({
            "id": __import__("uuid").uuid4(),
            "case_id": dto.case_id,
            "doc_type": "legal_notice",
            "title": "Legal Notice Draft",
            "content": result.updated_notice,
            "status": "draft",
        })

    return result


@router.post("/execute", response_model=ExecuteActionResponse)
async def execute_action(
    dto: ExecuteActionRequest,
    user_id: str = Depends(AuthHelper.get_current_user_id),
) -> ExecuteActionResponse:
    supabase = SupabaseService()
    rag = RagService()
    agent = AgentService(rag)
    return await agent.execute_action(dto, supabase_service=supabase)

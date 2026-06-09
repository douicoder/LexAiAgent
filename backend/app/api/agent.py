from fastapi import APIRouter, Depends

from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO, ChatRequestDTO, ChatResponseDTO
from app.helpers.auth_helper import AuthHelper
from app.services.agent_service import AgentService
from app.services.rag_service import RagService

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
    rag = RagService()
    agent = AgentService(rag)
    return await agent.chat(dto)

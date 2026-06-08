from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO, ChatRequestDTO, ChatResponseDTO
from app.interfaces.i_agent_service import IAgentService


class AgentService(IAgentService):
    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        raise NotImplementedError("Agent service will be implemented after account/auth.")

    async def chat(self, request: ChatRequestDTO) -> ChatResponseDTO:
        raise NotImplementedError("Agent chat will be implemented after account/auth.")

from abc import ABC, abstractmethod

from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO, ChatRequestDTO, ChatResponseDTO


class IAgentService(ABC):
    @abstractmethod
    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        ...

    @abstractmethod
    async def chat(self, request: ChatRequestDTO) -> ChatResponseDTO:
        ...

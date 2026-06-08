from abc import ABC, abstractmethod

from app.dto.agent_dto import GeneratePdfDTO, PdfResponseDTO


class IPdfService(ABC):
    @abstractmethod
    async def generate_pdf(self, request: GeneratePdfDTO) -> PdfResponseDTO:
        ...

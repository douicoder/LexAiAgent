from app.dto.agent_dto import GeneratePdfDTO, PdfResponseDTO
from app.interfaces.i_pdf_service import IPdfService


class PdfService(IPdfService):
    async def generate_pdf(self, request: GeneratePdfDTO) -> PdfResponseDTO:
        raise NotImplementedError("PDF service will be implemented after account/auth.")

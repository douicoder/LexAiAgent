import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO
from app.services.agent_service import AgentService
from app.services.pdf_service import PdfService
from app.services.rag_service import RagService

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

rag = RagService()
agent = AgentService(rag)


@router.post("/analyze")
async def demo_analyze(body: dict) -> AnalyzeResponseDTO:
    description = body.get("description", "")
    req = AnalyzeRequestDTO(
        case_id="demo",
        description=description,
        user_name="",
        opponent_name="",
        opponent_address="",
        language="en",
    )
    return await agent.analyze_case(req)


@router.post("/pdf")
async def demo_pdf(body: dict) -> StreamingResponse:
    legal_notice_draft = body.get("legal_notice_draft", "")
    user_name = body.get("user_name", "Sender")
    pdf_svc = PdfService()
    pdf_bytes = await pdf_svc.generate_legal_notice(
        notice_content=legal_notice_draft,
        user_details={"name": user_name, "address": "", "phone": None},
        recipient_details={"name": "", "address": ""},
        sections=body.get("relevant_sections", []),
        case_type=body.get("case_type", "civil"),
    )
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="legal_notice.pdf"'},
    )

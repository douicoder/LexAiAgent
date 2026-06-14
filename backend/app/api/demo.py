import io
import json
import logging
import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.dto.agent_dto import AnalyzeRequestDTO, AnalyzeResponseDTO
from app.services.agent_service import AgentService, AVAILABLE_LAW_DOCS
from app.services.pdf_service import PdfService
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@router.get("/health")
async def demo_health() -> dict[str, str]:
    return {"status": "ok", "service": "LexAgent Demo"}

rag = RagService()
agent = AgentService(rag)


async def keepalive_stream(task_coro):
    """Yield spaces to keep connection alive until the task completes."""
    task = asyncio.create_task(task_coro)
    while not task.done():
        yield b" "
        await asyncio.sleep(5)
    
    try:
        result = await task
        if hasattr(result, "model_dump_json"):
            yield result.model_dump_json().encode("utf-8")
        else:
            yield json.dumps(result).encode("utf-8")
    except Exception as e:
        logger.exception("Task failed in keepalive_stream")
        error_res = {"error": str(e), "message": "An error occurred during processing."}
        yield json.dumps(error_res).encode("utf-8")


@router.post("/improve-prompt")
async def demo_improve_prompt(body: dict):
    async def _process():
        description = body.get("description", "")
        logger.info(f"Improve prompt request: {len(description)} chars")
        if not description.strip():
            return {"improved": "", "original": ""}
        try:
            improved = await agent.improve_prompt(description)
            logger.info(f"Improve prompt complete: {len(improved)} chars")
            return {"improved": improved, "original": description}
        except Exception as e:
            logger.exception("Improve prompt failed")
            return {"improved": description, "original": description}
    return StreamingResponse(keepalive_stream(_process()), media_type="application/json")


@router.post("/analyze")
async def demo_analyze(body: dict):
    async def _process():
        description = body.get("description", "")
        logger.info(f"Analyze request: {len(description)} chars")
        if not description.strip():
            return AnalyzeResponseDTO(
                case_type="other",
                severity="low",
                legal_domain="Other",
                relevant_sections=[],
                summary="",
                next_steps=[],
                reasoning_trace="Empty description",
                ai_message="Please describe your legal problem so I can help you.",
                case_readiness_score=0,
                is_sufficient=False,
                law_docs_available=[],
                law_docs_coverage="",
            )
        try:
            request = AnalyzeRequestDTO(
                case_id="",
                description=description,
                user_name="",
                opponent_name="",
                opponent_address="",
            )
            result = await agent.analyze_case(request)
            logger.info(f"Analyze complete: score={result.case_readiness_score}, type={result.case_type}")
            return result
        except Exception as e:
            logger.exception("Analysis failed")
            docs_list = ", ".join(AVAILABLE_LAW_DOCS) if AVAILABLE_LAW_DOCS else "none available"
            return AnalyzeResponseDTO(
                case_type="other",
                severity="low",
                legal_domain="Other",
                relevant_sections=[],
                summary="",
                next_steps=[],
                reasoning_trace=f"Error: {e}",
                ai_message=f"Not enough data to proceed. Currently our database only has documents regarding: {docs_list}. Please provide more details about your case.",
                case_readiness_score=0,
                is_sufficient=False,
                law_docs_available=AVAILABLE_LAW_DOCS,
                law_docs_coverage="",
            )
    return StreamingResponse(keepalive_stream(_process()), media_type="application/json")


@router.post("/update-evidence")
async def demo_update_evidence(body: dict):
    async def _process():
        description = body.get("description", "")
        evidence_available = body.get("evidence_available", [])
        evidence_missing = body.get("evidence_missing", [])
        document_modifications = body.get("document_modifications", {})
        try:
            return await agent.update_evidence(description, evidence_available, evidence_missing, document_modifications)
        except Exception as e:
            logger.exception("Evidence update failed")
            return AnalyzeResponseDTO(
                case_type="other",
                severity="low",
                legal_domain="Other",
                relevant_sections=[],
                summary="",
                next_steps=[],
                reasoning_trace=f"Error: {e}",
                ai_message="Unable to update evidence. Please try again.",
                case_readiness_score=0,
                is_sufficient=False,
                law_docs_available=[],
                law_docs_coverage="",
            )
    return StreamingResponse(keepalive_stream(_process()), media_type="application/json")


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

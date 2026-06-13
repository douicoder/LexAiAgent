import datetime
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.dto.agent_dto import DocumentDTO, PdfResponseDTO
from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO, CreateCaseDTO, MessageDTO
from app.helpers.auth_helper import AuthHelper
from app.services.agent_service import AgentService
from app.services.case_message_service import CaseMessageService
from app.services.case_service import CaseService
from app.services.pdf_service import PdfService
from app.services.rag_service import RagService
from app.services.supabase_db import SupabaseService

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponseDTO, status_code=201)
async def create_case(
    dto: CreateCaseDTO,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> CaseResponseDTO:
    supabase = SupabaseService()
    service = CaseService(supabase, AgentService(RagService()))
    result = await service.create_case(dto, current_user_id)
    return result


@router.get("", response_model=CaseListResponseDTO)
async def list_cases(
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> CaseListResponseDTO:
    supabase = SupabaseService()
    service = CaseService(supabase)
    return await service.list_cases(current_user_id)


@router.get("/{case_id}", response_model=CaseDetailDTO)
async def get_case(
    case_id: str,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> CaseDetailDTO:
    supabase = SupabaseService()
    service = CaseService(supabase)
    return await service.get_case(case_id, current_user_id)


@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> dict:
    supabase = SupabaseService()
    service = CaseService(supabase)
    await service.delete_case(case_id, current_user_id)
    return {"deleted": True}


@router.post("/{case_id}/pdf", response_model=PdfResponseDTO)
async def generate_case_pdf(
    case_id: str,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> PdfResponseDTO:
    supabase = SupabaseService()
    case = supabase.get_case(case_id, current_user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.get("legal_notice_draft"):
        raise HTTPException(
            status_code=400,
            detail="Case has no legal notice draft. Analyze the case first.",
        )

    user = supabase.get_user(current_user_id)
    user_name = user.get("full_name", "Sender") if user else "Sender"

    pdf_svc = PdfService()
    pdf_bytes = await pdf_svc.generate_legal_notice(
        notice_content=case["legal_notice_draft"],
        user_details={"name": user_name, "address": "", "phone": None},
        recipient_details={"name": "", "address": ""},
        sections=case.get("relevant_sections") or [],
        case_type=case.get("case_type") or "civil",
    )

    url = await pdf_svc.upload_to_storage(pdf_bytes, f"{case_id}.pdf")

    supabase.update_case(case_id, {
        "pdf_url": url,
        "pdf_id": case_id,
        "status": "notice_generated",
    })

    return PdfResponseDTO(
        pdf_url=url,
        pdf_id=case_id,
        generated_at=str(datetime.datetime.now(datetime.timezone.utc)),
    )


@router.get("/{case_id}/messages")
async def get_case_messages(
    case_id: str,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
):
    supabase = SupabaseService()
    msg_service = CaseMessageService(supabase)
    messages = msg_service.get_messages(case_id, current_user_id)
    return [
        MessageDTO(
            id=m["id"],
            role=m["role"],
            content=m["content"],
            created_at=m["created_at"],
        )
        for m in messages
    ]


# ── Document CRUD ──────────────────────────────────────────────────────────


@router.get("/{case_id}/documents")
async def list_documents(
    case_id: str,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
):
    supabase = SupabaseService()
    case = supabase.get_case(case_id, current_user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    docs = supabase.get_documents(case_id)
    return [
        DocumentDTO(
            id=d["id"],
            case_id=d["case_id"],
            doc_type=d["doc_type"],
            title=d["title"],
            content=d["content"],
            status=d.get("status", "draft"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at"),
        )
        for d in docs
    ]


@router.put("/{case_id}/documents/{doc_id}")
async def update_document(
    case_id: str,
    doc_id: str,
    body: dict,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
):
    supabase = SupabaseService()
    case = supabase.get_case(case_id, current_user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = supabase.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    content = body.get("content", doc["content"])
    updated = supabase.update_document(doc_id, {"content": content, "status": body.get("status", doc.get("status", "draft"))})
    return DocumentDTO(
        id=updated["id"],
        case_id=updated["case_id"],
        doc_type=updated["doc_type"],
        title=updated["title"],
        content=updated["content"],
        status=updated.get("status", "draft"),
        created_at=updated.get("created_at", ""),
        updated_at=updated.get("updated_at"),
    )


@router.post("/{case_id}/documents/{doc_id}/preview")
async def preview_document_pdf(
    case_id: str,
    doc_id: str,
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
):
    supabase = SupabaseService()
    case = supabase.get_case(case_id, current_user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = supabase.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    user = supabase.get_user(current_user_id)
    user_name = user.get("full_name", "Sender") if user else "Sender"

    pdf_svc = PdfService()
    pdf_bytes = await pdf_svc.generate_legal_notice(
        notice_content=doc["content"],
        user_details={"name": user_name, "address": "", "phone": None},
        recipient_details={"name": "", "address": ""},
        sections=[],
        case_type="civil",
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc["title"]}.pdf"',
        },
    )

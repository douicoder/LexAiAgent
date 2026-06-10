import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dto.agent_dto import PdfResponseDTO
from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO, CreateCaseDTO
from app.helpers.auth_helper import AuthHelper
from app.models.case import Case
from app.models.user import User
from app.services.agent_service import AgentService
from app.services.case_service import CaseService
from app.services.pdf_service import PdfService
from app.services.rag_service import RagService

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponseDTO, status_code=201)
async def create_case(
    dto: CreateCaseDTO,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> CaseResponseDTO:
    service = CaseService(db, AgentService(RagService()))
    return await service.create_case(dto, current_user_id)


@router.get("", response_model=CaseListResponseDTO)
async def list_cases(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> CaseListResponseDTO:
    service = CaseService(db)
    return await service.list_cases(current_user_id)


@router.get("/{case_id}", response_model=CaseDetailDTO)
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> CaseDetailDTO:
    service = CaseService(db)
    return await service.get_case(case_id, current_user_id)


@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> dict:
    service = CaseService(db)
    await service.delete_case(case_id, current_user_id)
    return {"deleted": True}


@router.post("/{case_id}/pdf", response_model=PdfResponseDTO)
async def generate_case_pdf(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> PdfResponseDTO:
    uid = uuid.UUID(current_user_id) if isinstance(current_user_id, str) else current_user_id
    cid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id

    result = await db.execute(
        select(Case).where(Case.id == cid, Case.user_id == uid)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.legal_notice_draft:
        raise HTTPException(
            status_code=400,
            detail="Case has no legal notice draft. Analyze the case first.",
        )

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    user_name = user.full_name if user else "Sender"

    pdf_svc = PdfService()
    pdf_bytes = await pdf_svc.generate_legal_notice(
        notice_content=case.legal_notice_draft,
        user_details={"name": user_name, "address": "", "phone": None},
        recipient_details={"name": "", "address": ""},
        sections=case.relevant_sections or [],
        case_type=case.case_type or "civil",
    )

    url = await pdf_svc.upload_to_storage(pdf_bytes, f"{case_id}.pdf")

    case.pdf_url = url
    case.pdf_id = case_id
    case.status = "notice_generated"
    await db.commit()

    return PdfResponseDTO(
        pdf_url=url,
        pdf_id=case_id,
        generated_at=str(datetime.datetime.utcnow()),
    )

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.agent_dto import AnalyzeRequestDTO
from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO, CreateCaseDTO
from app.interfaces.i_agent_service import IAgentService
from app.interfaces.i_case_service import ICaseService
from app.mapper.auto_mapper import AutoMapper
from app.models.case import Case


class CaseService(ICaseService):
    def __init__(self, db: AsyncSession, agent: IAgentService | None = None):
        self.db = db
        self.agent = agent

    async def create_case(self, dto: CreateCaseDTO, user_id: str) -> CaseResponseDTO:
        case = Case(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
            description=dto.description,
            language=dto.language,
            status="processing",
        )
        self.db.add(case)
        await self.db.commit()
        await self.db.refresh(case)

        analyze_req = AnalyzeRequestDTO(
            case_id=str(case.id),
            description=dto.description,
            user_name="",
            opponent_name="",
            opponent_address="",
            language=dto.language,
        )
        result = await self.agent.analyze_case(analyze_req)

        case.case_type = result.case_type
        case.severity = result.severity
        case.status = "analyzed"
        case.relevant_sections = [
            {
                "act": s.get("act", ""),
                "section": str(s.get("section_number") or s.get("section", "")),
                "title": s.get("section_title") or s.get("title", ""),
                "excerpt": s.get("excerpt", ""),
                "relevance_score": float(s.get("score", 0) or 0),
            }
            for s in (result.relevant_sections or [])
        ]
        case.summary = result.summary
        case.next_steps = [ns.model_dump() for ns in (result.next_steps or [])]
        case.agent_reasoning = result.reasoning_trace
        case.legal_notice_draft = result.legal_notice_draft
        case.ai_message = result.ai_message
        case.clarifying_questions = [cq.model_dump() for cq in (result.clarifying_questions or [])]
        case.action_buttons = [ab.model_dump() for ab in (result.action_buttons or [])]
        await self.db.commit()
        await self.db.refresh(case)

        return AutoMapper.case_to_response_dto(case)

    async def get_case(self, case_id: str, user_id: str) -> CaseDetailDTO:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        cid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id
        result = await self.db.execute(
            select(Case).where(Case.id == cid, Case.user_id == uid)
        )
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return AutoMapper.case_to_detail_dto(case)

    async def list_cases(self, user_id: str) -> CaseListResponseDTO:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        result = await self.db.execute(
            select(Case)
            .where(Case.user_id == uid)
            .order_by(Case.created_at.desc())
        )
        cases = result.scalars().all()
        return CaseListResponseDTO(
            cases=AutoMapper.case_list_to_dto(list(cases)),
            total=len(cases),
        )

    async def delete_case(self, case_id: str, user_id: str) -> bool:
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        cid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id
        result = await self.db.execute(
            select(Case).where(Case.id == cid, Case.user_id == uid)
        )
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        await self.db.delete(case)
        await self.db.commit()
        return True

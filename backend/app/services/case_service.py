import logging
import uuid

from fastapi import HTTPException

logger = logging.getLogger(__name__)

from app.dto.agent_dto import AnalyzeRequestDTO
from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO, CreateCaseDTO
from app.services.agent_service import AgentService
from app.mapper.auto_mapper import AutoMapper
from app.services.case_message_service import CaseMessageService
from app.services.supabase_db import SupabaseService


class CaseService:
    def __init__(self, supabase: SupabaseService, agent: AgentService | None = None):
        self.supabase = supabase
        self.agent = agent

    async def create_case(self, dto: CreateCaseDTO, user_id: str) -> CaseResponseDTO:
        case_id = str(uuid.uuid4())

        case = self.supabase.create_case({
            "id": case_id,
            "user_id": user_id,
            "description": dto.description,
            "language": dto.language,
            "status": "processing",
        })

        analyze_req = AnalyzeRequestDTO(
            case_id=case_id,
            description=dto.description,
            user_name="",
            opponent_name="",
            opponent_address="",
            language=dto.language,
        )
        result = await self.agent.analyze_case(analyze_req)

        sections = [
            {
                "act": s.get("act", ""),
                "section": str(s.get("section_number") or s.get("section", "")),
                "title": s.get("section_title") or s.get("title", ""),
                "excerpt": s.get("excerpt", ""),
                "relevance_score": float(s.get("score", 0) or 0),
            }
            for s in (result.relevant_sections or [])
        ]

        updated = self.supabase.update_case(case_id, {
            "case_type": result.case_type,
            "severity": result.severity,
            "status": "analyzed",
            "relevant_sections": sections,
            "summary": result.summary,
            "next_steps": [ns.model_dump() for ns in (result.next_steps or [])],
            "agent_reasoning": result.reasoning_trace,
            "legal_notice_draft": result.legal_notice_draft,
            "ai_message": result.ai_message,
            "clarifying_questions": [cq.model_dump() for cq in (result.clarifying_questions or [])],
            "action_buttons": [ab.model_dump() for ab in (result.action_buttons or [])],
        })

        # Save v2 fields (may fail if Supabase table lacks columns — handle gracefully)
        try:
            self.supabase.update_case(case_id, {
                "legal_domain": result.legal_domain,
                "case_readiness_score": result.case_readiness_score,
                "evidence_available": result.evidence_available,
                "evidence_missing": result.evidence_missing,
                "risk_level": result.risk_level,
                "recommended_actions": result.recommended_actions,
            })
        except Exception as e:
            logger.warning("Could not save v2 analysis fields (columns may not exist yet): %s", e)

        msg_service = CaseMessageService(self.supabase)
        msg_service.add_message(case_id, "user", dto.description)
        msg_service.add_message(
            case_id, "assistant", result.ai_message or "",
            extra_data={
                "case_type": result.case_type,
                "severity": result.severity,
                "legal_domain": result.legal_domain,
                "summary": result.summary,
                "legal_notice_draft": result.legal_notice_draft,
                "relevant_sections": result.relevant_sections,
                "next_steps": [ns.model_dump() for ns in (result.next_steps or [])],
                "reasoning_trace": result.reasoning_trace,
                "case_readiness_score": result.case_readiness_score,
                "evidence_available": result.evidence_available,
                "evidence_missing": result.evidence_missing,
                "risk_level": result.risk_level,
                "recommended_actions": result.recommended_actions,
            },
        )

        # Merge agent data into DB response (v2 fields may not be saved to Supabase yet)
        dto = AutoMapper.case_to_response_dto(updated)
        dto.legal_domain = result.legal_domain or dto.legal_domain
        dto.case_readiness_score = result.case_readiness_score or dto.case_readiness_score
        dto.evidence_available = result.evidence_available or dto.evidence_available
        dto.evidence_missing = result.evidence_missing or dto.evidence_missing
        dto.risk_level = result.risk_level or dto.risk_level
        dto.recommended_actions = result.recommended_actions or dto.recommended_actions
        return dto

    async def get_case(self, case_id: str, user_id: str) -> CaseDetailDTO:
        case = self.supabase.get_case(case_id, user_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return AutoMapper.case_to_detail_dto(case)

    async def list_cases(self, user_id: str) -> CaseListResponseDTO:
        cases = self.supabase.list_cases(user_id)
        return CaseListResponseDTO(
            cases=AutoMapper.case_list_to_dto(cases),
            total=len(cases),
        )

    async def delete_case(self, case_id: str, user_id: str) -> bool:
        deleted = self.supabase.delete_case(case_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Case not found")
        return True

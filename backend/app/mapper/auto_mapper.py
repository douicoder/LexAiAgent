from datetime import datetime

from app.dto.auth_dto import UserProfileDTO
from app.dto.case_dto import CaseDetailDTO, CaseResponseDTO


class AutoMapper:
    @staticmethod
    def user_to_profile_dto(user: dict, case_count: int = 0) -> UserProfileDTO:
        return UserProfileDTO(
            email=user.get("email", ""),
            full_name=user.get("full_name", ""),
            preferred_language=user.get("preferred_language", "en"),
            case_count=case_count,
        )

    @staticmethod
    def case_to_response_dto(case: dict) -> CaseResponseDTO:
        created = case.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                created = None

        return CaseResponseDTO(
            case_id=str(case.get("id", "")),
            status=case.get("status", "processing"),
            case_type=case.get("case_type"),
            severity=case.get("severity"),
            relevant_sections=case.get("relevant_sections") or [],
            summary=case.get("summary"),
            next_steps=case.get("next_steps") or [],
            pdf_ready=bool(case.get("pdf_url")),
            created_at=created,
            ai_message=case.get("ai_message"),
            clarifying_questions=case.get("clarifying_questions") or [],
            action_buttons=case.get("action_buttons") or [],
        )

    @staticmethod
    def case_to_detail_dto(case: dict) -> CaseDetailDTO:
        base = AutoMapper.case_to_response_dto(case)
        return CaseDetailDTO(
            **base.model_dump(),
            description=case.get("description", ""),
            agent_reasoning=case.get("agent_reasoning"),
            legal_notice_draft=case.get("legal_notice_draft"),
            pdf_url=case.get("pdf_url"),
        )

    @staticmethod
    def case_list_to_dto(cases: list[dict]) -> list[CaseResponseDTO]:
        return [AutoMapper.case_to_response_dto(case) for case in cases]

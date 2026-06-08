from app.dto.auth_dto import AuthResponseDTO, UserProfileDTO
from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO
from app.models.case import Case
from app.models.user import User


class AutoMapper:
    @staticmethod
    def user_to_auth_response(user: User, token: str) -> AuthResponseDTO:
        return AuthResponseDTO(
            email=user.email,
            full_name=user.full_name,
            access_token=token,
        )

    @staticmethod
    def user_to_profile_dto(user: User, case_count: int = 0) -> UserProfileDTO:
        return UserProfileDTO(
            email=user.email,
            full_name=user.full_name,
            preferred_language=user.preferred_language,
            case_count=case_count,
        )

    @staticmethod
    def case_to_response_dto(case: Case) -> CaseResponseDTO:
        return CaseResponseDTO(
            case_id=str(case.id),
            status=case.status,
            case_type=case.case_type,
            severity=case.severity,
            relevant_sections=case.relevant_sections or [],
            summary=case.summary,
            next_steps=case.next_steps or [],
            pdf_ready=bool(case.pdf_url),
            created_at=case.created_at,
        )

    @staticmethod
    def case_to_detail_dto(case: Case) -> CaseDetailDTO:
        base = AutoMapper.case_to_response_dto(case)
        return CaseDetailDTO(
            **base.model_dump(),
            description=case.description,
            agent_reasoning=case.agent_reasoning,
            legal_notice_draft=case.legal_notice_draft,
            pdf_url=case.pdf_url,
        )

    @staticmethod
    def case_list_to_dto(cases: list[Case]) -> CaseListResponseDTO:
        mapped_cases = [AutoMapper.case_to_response_dto(case) for case in cases]
        return CaseListResponseDTO(cases=mapped_cases, total=len(mapped_cases))

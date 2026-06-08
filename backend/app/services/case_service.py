from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO, CreateCaseDTO
from app.interfaces.i_case_service import ICaseService


class CaseService(ICaseService):
    async def create_case(self, dto: CreateCaseDTO, user_id: str) -> CaseResponseDTO:
        raise NotImplementedError("Case service will be implemented after account/auth.")

    async def get_case(self, case_id: str, user_id: str) -> CaseDetailDTO:
        raise NotImplementedError("Case service will be implemented after account/auth.")

    async def list_cases(self, user_id: str) -> CaseListResponseDTO:
        raise NotImplementedError("Case service will be implemented after account/auth.")

    async def delete_case(self, case_id: str, user_id: str) -> bool:
        raise NotImplementedError("Case service will be implemented after account/auth.")

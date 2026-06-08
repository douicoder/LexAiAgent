from abc import ABC, abstractmethod

from app.dto.case_dto import CaseDetailDTO, CaseListResponseDTO, CaseResponseDTO, CreateCaseDTO


class ICaseService(ABC):
    @abstractmethod
    async def create_case(self, dto: CreateCaseDTO, user_id: str) -> CaseResponseDTO:
        ...

    @abstractmethod
    async def get_case(self, case_id: str, user_id: str) -> CaseDetailDTO:
        ...

    @abstractmethod
    async def list_cases(self, user_id: str) -> CaseListResponseDTO:
        ...

    @abstractmethod
    async def delete_case(self, case_id: str, user_id: str) -> bool:
        ...

from abc import ABC, abstractmethod


class IRagService(ABC):
    @abstractmethod
    async def search(self, query: str, top_k: int = 5, acts: list[str] | None = None) -> list[dict]:
        ...

    @abstractmethod
    async def ingest_document(self, pdf_path: str, act_name: str) -> bool:
        ...

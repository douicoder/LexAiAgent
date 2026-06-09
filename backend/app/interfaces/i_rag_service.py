from abc import ABC, abstractmethod


class IRagService(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        acts: list[str] | None = None,
        min_relevance_score: float = 0.0,
        use_hybrid: bool = True,
        use_rerank: bool = False,
        vector_weight: float = 0.7,
    ) -> list[dict]:
        ...

    @abstractmethod
    async def ingest_document(self, pdf_path: str, act_name: str) -> bool:
        ...

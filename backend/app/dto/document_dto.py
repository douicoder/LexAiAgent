from pydantic import BaseModel


class SearchRequestDTO(BaseModel):
    query: str
    top_k: int = 5
    acts: list[str] | None = None


class LawSearchResultDTO(BaseModel):
    act: str
    section: str
    title: str
    excerpt: str
    relevance_score: float


class SearchResponseDTO(BaseModel):
    results: list[LawSearchResultDTO]
    query: str
    total: int

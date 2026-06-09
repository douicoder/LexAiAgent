from pydantic import BaseModel


class SearchRequestDTO(BaseModel):
    query: str
    top_k: int = 5
    acts: list[str] | None = None
    min_score: float = 0.0
    use_hybrid: bool = True
    use_rerank: bool = False
    vector_weight: float = 0.7


class LawSearchResultDTO(BaseModel):
    act: str
    chapter: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    score: float
    excerpt: str


class SearchResponseDTO(BaseModel):
    results: list[LawSearchResultDTO]
    query: str
    total: int

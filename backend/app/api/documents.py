from fastapi import APIRouter, Query

from app.dto.document_dto import LawSearchResultDTO, SearchResponseDTO
from app.services.rag_service import RagService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/search", response_model=SearchResponseDTO)
async def search_documents(
    q: str = Query(..., min_length=2),
    top_k: int = Query(5, ge=1, le=20),
    acts: str | None = None,
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    hybrid: bool = Query(True, description="Enable hybrid vector+BM25 search"),
    rerank: bool = Query(False, description="Enable cross-encoder reranking"),
    vector_weight: float = Query(0.7, ge=0.0, le=1.0, description="Weight for vector score in hybrid fusion"),
) -> SearchResponseDTO:
    act_filters = [act.strip() for act in acts.split(",") if act.strip()] if acts else None
    rag = RagService()
    results = await rag.search(
        q,
        top_k=top_k,
        acts=act_filters,
        min_relevance_score=min_score,
        use_hybrid=hybrid,
        use_rerank=rerank,
        vector_weight=vector_weight,
    )
    return SearchResponseDTO(
        results=[LawSearchResultDTO(**r) for r in results],
        query=q,
        total=len(results),
    )

@router.get("/health")
async def health_check():
    return {"status": "ok"}
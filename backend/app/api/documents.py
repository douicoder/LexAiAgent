from fastapi import APIRouter, Query

from app.dto.document_dto import SearchResponseDTO
from app.services.rag_service import RagService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/search", response_model=SearchResponseDTO)
async def search_documents(
    q: str = Query(..., min_length=2),
    top_k: int = Query(5, ge=1, le=20),
    acts: str | None = None,
) -> SearchResponseDTO:
    act_filter = [act.strip() for act in acts.split(",") if act.strip()] if acts else None
    rag = RagService()
    results = await rag.search(q, top_k=top_k, acts=act_filter)
    return SearchResponseDTO(results=results, query=q, total=len(results))

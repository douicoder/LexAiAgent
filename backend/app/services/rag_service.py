import logging

from fastapi import HTTPException, status
from openai import OpenAI
from supabase import create_client

from app.config import settings
from app.interfaces.i_rag_service import IRagService

logger = logging.getLogger(__name__)


def _squash_bm25(score: float) -> float:
    """Squash unbounded BM25 score into [0, 1) using sigmoid-like transform."""
    return score / (score + 1.0)


class RagService(IRagService):
    def __init__(self):
        if not settings.GITHUB_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GITHUB_TOKEN is required for RAG embeddings.",
            )
        self.client = OpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_URL and SUPABASE_KEY must be set.",
            )
        self.supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.embedding_model = settings.EMBEDDING_MODEL

        # Lazy-loaded resources
        self._reranker = None

    # ── Embedding ──────────────────────────────────────────────────────────
    async def _embed_text(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text,
            dimensions=1536,
        )
        return response.data[0].embedding

    # ── Reranker lazy init ─────────────────────────────────────────────────
    def _ensure_reranker(self):
        if self._reranker is not None:
            return True
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Reranker loaded")
            return True
        except Exception:
            logger.warning("Reranker not available; install sentence-transformers")
            self._reranker = False
            return False

    def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        if not candidates:
            return candidates
        pairs = [[query, c["excerpt"]] for c in candidates]
        try:
            scores = self._reranker.predict(pairs)
            for c, s in zip(candidates, scores):
                c["rerank_score"] = round(float(s), 4)
            candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        except Exception as e:
            logger.warning("Reranking failed: %s", e)
        return candidates

    # ── Search ─────────────────────────────────────────────────────────────
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
        # 1. Embed query
        query_vec = await self._embed_text(query)

        # 2. Fetch candidates via Supabase pgvector RPC
        data = self.supabase.rpc(
            "match_law_chunks",
            {
                "query_embedding": query_vec,
                "match_count": top_k * 2,
            }
        ).execute().data
        if not data:
            return []
        if acts:
            data = [row for row in data if row["act_name"] in acts]
            if not data:
                return []

        # 3. Map RPC similarity as vector score
        for row in data:
            row["_vec_score"] = row["similarity"]

        # 4. BM25 scores if hybrid (on RPC results only)
        bm25_scores = None
        if use_hybrid:
            try:
                from rank_bm25 import BM25Okapi
                tokenized_query = query.split()
                rpc_texts = [row["chunk_text"] for row in data]
                tokenized_rpc = [t.split() for t in rpc_texts]
                temp_bm25 = BM25Okapi(tokenized_rpc)
                raw = temp_bm25.get_scores(tokenized_query)
                bm25_scores = [_squash_bm25(s) for s in raw]
            except Exception as e:
                logger.warning("BM25 scoring on RPC results failed: %s", e)
                bm25_scores = None

        # 5. Build results
        scored = []
        for i, row in enumerate(data):
            vec_score = row["_vec_score"]
            if vec_score < min_relevance_score and not use_hybrid:
                continue

            if bm25_scores is not None and i < len(bm25_scores):
                bm25 = bm25_scores[i]
                fused = vector_weight * vec_score + (1 - vector_weight) * bm25
            else:
                fused = vec_score
                bm25 = None

            if fused < min_relevance_score:
                continue

            meta = row.get("metadata", {}) or {}

            scored.append({
                "act": row["act_name"],
                "chapter": meta.get("chapter"),
                "section_number": meta.get("section_number"),
                "section_title": meta.get("section_title"),
                "score": round(fused, 3),
                "vector_score": round(vec_score, 3),
                "bm25_score": round(bm25, 3) if bm25 is not None else None,
                "excerpt": row["chunk_text"][:300],
            })

        # 6. Sort by fused score
        scored.sort(key=lambda x: x["score"], reverse=True)

        # 7. Optional reranking on top candidates
        if use_rerank and self._ensure_reranker():
            top_to_rerank = scored[:top_k * 2]
            rest = scored[top_k * 2:]
            top_to_rerank = self._rerank(query, top_to_rerank)
            scored = top_to_rerank + rest

        return scored[:top_k]

    async def ingest_document(self, pdf_path: str, act_name: str) -> bool:
        raise NotImplementedError("Ingestion is performed via ingest_laws.py using Supabase client.")

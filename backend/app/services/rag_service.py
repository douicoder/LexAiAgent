import ast
import logging

import numpy as np
from fastapi import HTTPException, status
from openai import OpenAI
from supabase import create_client

from app.config import settings
from app.interfaces.i_rag_service import IRagService

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-8))


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
        self._bm25 = None
        self._corpus_texts: list[str] | None = None
        self._reranker = None

    # ── Embedding ──────────────────────────────────────────────────────────
    async def _embed_text(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text,
            dimensions=1536,
        )
        return response.data[0].embedding

    # ── BM25 lazy init ─────────────────────────────────────────────────────
    def _ensure_bm25(self):
        if self._bm25 is not None:
            return
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25 not installed; hybrid search disabled.")
            self._bm25 = False
            return

        data = self.supabase.table("law_chunks").select("chunk_text").execute().data
        self._corpus_texts = [row["chunk_text"] for row in data]
        tokenized_corpus = [t.split() for t in self._corpus_texts]
        self._bm25 = BM25Okapi(tokenized_corpus)
        logger.info("BM25 index built with %d documents", len(self._corpus_texts))

    def _bm25_scores(self, query: str) -> list[float] | None:
        if not self._bm25:
            return None
        tokenized_query = query.split()
        raw = self._bm25.get_scores(tokenized_query)
        return [_squash_bm25(s) for s in raw]

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

        # 2. Fetch candidates from Supabase
        supabase_query = self.supabase.table("law_chunks").select(
            "id, act_name, chunk_text, embedding, metadata"
        )
        if acts:
            act_filter = ",".join([f"act_name.eq.{a}" for a in acts])
            supabase_query = supabase_query.or_(act_filter)
        data = supabase_query.execute().data
        if not data:
            return []

        # 3. Compute vector scores
        for row in data:
            emb = row["embedding"]
            if isinstance(emb, str):
                try:
                    emb = ast.literal_eval(emb)
                except Exception:
                    emb = [float(x) for x in emb.strip("[]").split(",") if x]
            row["_vec_score"] = _cosine_similarity(query_vec, emb)

        # 4. BM25 scores if hybrid
        bm25_scores = None
        if use_hybrid:
            self._ensure_bm25()
            if self._bm25:
                try:
                    bm25_scores = self._bm25_scores(query)
                except Exception:
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

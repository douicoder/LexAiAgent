from pathlib import Path

from fastapi import HTTPException, status
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.supabase import SupabaseVectorStore

from app.config import settings
from app.interfaces.i_rag_service import IRagService


class RagService(IRagService):
    def __init__(self):
        if not settings.GITHUB_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GITHUB_TOKEN is required for RAG embeddings.",
            )

        if not settings.DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="RAG requires DATABASE_URL to point to a Postgres database with pgvector enabled.",
            )

        self.embed_model = OpenAIEmbedding(
            model="text-embedding-3-small",
            api_key=settings.GITHUB_TOKEN,
            api_base="https://models.inference.ai.azure.com",
        )
        Settings.embed_model = self.embed_model

        self.vector_store = SupabaseVectorStore(
            postgres_connection_string=settings.DATABASE_URL,
            collection_name="law_chunks",
        )
        self.index = VectorStoreIndex.from_vector_store(self.vector_store)

    async def search(self, query: str, top_k: int = 5, acts: list[str] | None = None) -> list[dict]:
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        nodes = await retriever.aretrieve(query)

        results = []
        for node in nodes:
            meta = node.metadata
            if acts and meta.get("act_name") not in acts:
                continue

            results.append(
                {
                    "act": meta.get("act_name"),
                    "section": meta.get("section_number"),
                    "title": meta.get("section_title"),
                    "excerpt": node.text[:300],
                    "relevance_score": round(node.score or 0, 3),
                }
            )
        return results

    async def ingest_document(self, pdf_path: str, act_name: str) -> bool:
        path = Path(pdf_path)
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Law document not found: {pdf_path}",
            )

        docs = SimpleDirectoryReader(input_files=[str(path)]).load_data()
        for doc in docs:
            doc.metadata["act_name"] = act_name

        VectorStoreIndex.from_documents(
            docs,
            vector_store=self.vector_store,
        )
        return True

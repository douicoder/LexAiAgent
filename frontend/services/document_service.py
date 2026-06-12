from utils.api_client import APIClient


class DocumentService:
    def __init__(self, token: str | None = None):
        self.client = APIClient(token=token)

    def search(
        self,
        query: str,
        top_k: int = 10,
        acts: str | None = None,
        min_score: float = 0.0,
        hybrid: bool = True,
        rerank: bool = False,
        vector_weight: float = 0.7,
    ) -> dict:
        params: dict = {
            "q": query,
            "top_k": top_k,
            "min_score": min_score,
            "hybrid": str(hybrid).lower(),
            "rerank": str(rerank).lower(),
            "vector_weight": vector_weight,
        }
        if acts:
            params["acts"] = acts
        return self.client.get("/documents/search", params=params, auth=False)

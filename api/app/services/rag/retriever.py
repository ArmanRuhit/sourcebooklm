"""Notebook-scoped retrieval: similarity search, then MMR for diversity."""

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.services.vector_store import get_store

FETCH_K = 12
TOP_K = 6
MMR_LAMBDA = 0.5


async def retrieve(
    notebook_id: str,
    query: str,
    *,
    k: int = TOP_K,
    fetch_k: int = FETCH_K,
    embeddings: Embeddings | None = None,
) -> list[Document]:
    """Return up to `k` diverse chunks from one notebook only."""
    cleaned = query.strip()
    if not cleaned:
        return []

    k = max(1, k)
    fetch_k = max(k, fetch_k)
    store = await get_store(embeddings)
    return await store.amax_marginal_relevance_search(
        cleaned,
        k=k,
        fetch_k=fetch_k,
        lambda_mult=MMR_LAMBDA,
        filter={"notebook_id": notebook_id},
    )

"""Notebook-scoped retrieval: MMR per query, fused across query variants."""

import logging

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.services.rag import expansion, rerank
from app.services.vector_store import get_store

FETCH_K = 12
TOP_K = 6
MMR_LAMBDA = 0.5
RRF_K = 60

logger = logging.getLogger(__name__)


def _document_key(document: Document) -> tuple[str, object]:
    metadata = document.metadata
    return str(metadata.get("source_id", "")), metadata.get("chunk_index")


async def retrieve(
    notebook_id: str,
    query: str,
    *,
    k: int = TOP_K,
    fetch_k: int = FETCH_K,
    embeddings: Embeddings | None = None,
    lambda_mult: float = MMR_LAMBDA,
    expand: bool = False,
    use_rerank: bool = False,
) -> list[Document]:
    """Return up to `k` diverse chunks from one notebook only.

    With `expand=True`, an LLM proposes paraphrases, each is searched with MMR,
    and the ranked lists are fused with reciprocal rank fusion. The original
    query always leads, so a failed expansion still behaves like baseline.
    With `use_rerank=True`, an LLM reorders the fused candidates before `k` is
    applied. Both upgrades are best-effort and fall back to retrieval order.
    """
    cleaned = query.strip()
    if not cleaned:
        return []

    k = max(1, k)
    fetch_k = max(k, fetch_k)
    queries = await expansion.expand_question(cleaned) if expand else [cleaned]

    store = await get_store(embeddings)
    scores: dict[tuple[str, object], float] = {}
    documents: dict[tuple[str, object], Document] = {}

    for variant in queries:
        hits = await store.amax_marginal_relevance_search(
            variant,
            k=fetch_k,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
            filter={"notebook_id": notebook_id},
        )
        for rank, document in enumerate(hits):
            key = _document_key(document)
            documents.setdefault(key, document)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)

    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    candidates = [documents[key] for key in ordered[: max(k, fetch_k)]]

    if use_rerank and candidates:
        candidates = await rerank.rerank_documents(cleaned, candidates)

    return candidates[:k]

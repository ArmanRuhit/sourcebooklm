"""PGVector collection `chunks`: setup, indexing, and filtered search.

PGVector owns its two tables (`langchain_pg_collection`, `langchain_pg_embedding`),
so setup happens here instead of Alembic (technical design §3.2). The HNSW index
is created idempotently after the tables exist.
"""

import logging
from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from pydantic import SecretStr
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.services.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "chunks"
HNSW_INDEX_NAME = "ix_langchain_pg_embedding_hnsw"
EMBED_BATCH_SIZE = 100


class EmbeddingConfigError(RuntimeError):
    """Raised when embeddings are requested without a usable API key."""


def get_embeddings() -> OpenAIEmbeddings:
    """Build the OpenAI embedding client, failing clearly when unconfigured."""
    api_key = (settings.openai_api_key or "").strip()
    if not api_key or api_key.startswith("sk-..."):
        raise EmbeddingConfigError(
            "OPENAI_API_KEY is not configured; add a real key to api/.env to embed sources"
        )

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=SecretStr(api_key),
        max_retries=3,
    )


async def _ensure_hnsw_index() -> None:
    """Create the cosine HNSW index once; safe to run at every startup."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {HNSW_INDEX_NAME} "
                "ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)"
            )
        )


async def get_store(
    embeddings: Embeddings | None = None,
    *,
    collection_name: str = COLLECTION_NAME,
) -> PGVector:
    """Return a ready PGVector store (tables, collection, and HNSW index)."""
    store = PGVector(
        embeddings=embeddings or get_embeddings(),
        connection=engine,
        collection_name=collection_name,
        embedding_length=settings.embedding_dimensions,
        use_jsonb=True,
        create_extension=True,
    )
    await store.acreate_tables_if_not_exists()
    await store.acreate_collection()
    await _ensure_hnsw_index()
    return store


async def ensure_vector_store() -> None:
    """Startup hook: create the collection and index before the worker runs."""
    await get_store()
    logger.info("vector store '%s' ready", COLLECTION_NAME)


async def _delete_source_rows(source_id: str) -> None:
    """Delete vectors by metadata.

    langchain-postgres 0.0.19 `adelete()` only supports IDs and silently ignores
    metadata filters, so delete through the table directly.
    """
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM langchain_pg_embedding WHERE cmetadata->>'source_id' = :source_id"),
            {"source_id": source_id},
        )


async def index_chunks(
    *,
    notebook_id: str,
    source_id: str,
    source_type: str,
    title: str,
    chunks: Sequence[Chunk],
    embeddings: Embeddings | None = None,
) -> int:
    """Replace a source's vectors and return the number indexed."""
    if not chunks:
        raise ValueError("Cannot index an empty chunk list")

    store = await get_store(embeddings)
    # Re-indexing is delete-then-add; deterministic IDs keep retries idempotent.
    await _delete_source_rows(source_id)

    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        await store.aadd_texts(
            texts=[chunk.text for chunk in batch],
            metadatas=[
                {
                    "notebook_id": notebook_id,
                    "source_id": source_id,
                    "source_type": source_type,
                    "chunk_index": chunk.index,
                    "title": title,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    **({"page": chunk.page} if chunk.page is not None else {}),
                    **(
                        {"start_seconds": chunk.start_seconds}
                        if chunk.start_seconds is not None
                        else {}
                    ),
                    **({"end_seconds": chunk.end_seconds} if chunk.end_seconds is not None else {}),
                }
                for chunk in batch
            ],
            ids=[f"{source_id}:{chunk.index}" for chunk in batch],
        )

    return len(chunks)


async def delete_source(source_id: str) -> None:
    """Remove every vector belonging to a source (safe before tables exist)."""
    async with engine.begin() as connection:
        table = await connection.scalar(text("SELECT to_regclass('langchain_pg_embedding')"))
        if table is None:
            return
        await connection.execute(
            text("DELETE FROM langchain_pg_embedding WHERE cmetadata->>'source_id' = :source_id"),
            {"source_id": source_id},
        )


async def search_chunks(
    notebook_id: str,
    query: str,
    *,
    k: int = 4,
    embeddings: Embeddings | None = None,
) -> list[tuple[Document, float]]:
    """Similarity search restricted to one notebook (retrieval invariant)."""
    store = await get_store(embeddings)
    return await store.asimilarity_search_with_score(
        query,
        k=k,
        filter={"notebook_id": notebook_id},
    )

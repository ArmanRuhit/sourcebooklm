"""PGVector indexing tests: notebook isolation, idempotent re-index, HNSW."""

import uuid

from sqlalchemy import text

from app.db import async_session_factory, engine
from app.models import Notebook, Source
from app.services import sources as source_service
from app.services.ingestion.chunker import Chunk
from app.services.vector_store import (
    HNSW_INDEX_NAME,
    delete_source,
    get_store,
    index_chunks,
    search_chunks,
)
from tests.helpers import FakeEmbeddings


def _chunk(text: str, index: int = 0) -> Chunk:
    return Chunk(text=text, index=index, char_start=0, char_end=len(text))


async def test_search_filters_by_notebook() -> None:
    embeddings = FakeEmbeddings()
    notebook_a, notebook_b = str(uuid.uuid4()), str(uuid.uuid4())
    source_a, source_b = str(uuid.uuid4()), str(uuid.uuid4())

    try:
        await index_chunks(
            notebook_id=notebook_a,
            source_id=source_a,
            source_type="text",
            title="Notebook A source",
            chunks=[_chunk("alpha beta grounded answer"), _chunk("gamma delta", 1)],
            embeddings=embeddings,
        )
        await index_chunks(
            notebook_id=notebook_b,
            source_id=source_b,
            source_type="text",
            title="Notebook B source",
            chunks=[_chunk("alpha beta belongs to B")],
            embeddings=embeddings,
        )

        results = await search_chunks(notebook_a, "alpha beta", k=10, embeddings=embeddings)

        assert results
        assert all(document.metadata["notebook_id"] == notebook_a for document, _ in results)
        assert any("alpha beta" in document.page_content for document, _ in results)
        assert all(document.metadata["source_id"] == source_a for document, _ in results)
    finally:
        await delete_source(source_a)
        await delete_source(source_b)


async def test_reindex_replaces_a_sources_vectors() -> None:
    embeddings = FakeEmbeddings()
    notebook_id, source_id = str(uuid.uuid4()), str(uuid.uuid4())
    chunks = [_chunk("one two three four")]

    try:
        await index_chunks(
            notebook_id=notebook_id,
            source_id=source_id,
            source_type="text",
            title="Reindex me",
            chunks=chunks,
            embeddings=embeddings,
        )
        await index_chunks(
            notebook_id=notebook_id,
            source_id=source_id,
            source_type="text",
            title="Reindex me",
            chunks=chunks,
            embeddings=embeddings,
        )

        results = await search_chunks(notebook_id, "one two", k=10, embeddings=embeddings)
        matching = [
            document for document, _ in results if document.metadata["source_id"] == source_id
        ]
        assert len(matching) == 1
    finally:
        await delete_source(source_id)


async def test_hnsw_index_is_created() -> None:
    await get_store(FakeEmbeddings())

    async with engine.connect() as connection:
        found = await connection.scalar(
            text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
            {"name": HNSW_INDEX_NAME},
        )

    assert found == 1


async def test_deleting_a_source_removes_its_vectors() -> None:
    embeddings = FakeEmbeddings()
    async with async_session_factory() as session:
        notebook = Notebook(name="Vector delete test")
        session.add(notebook)
        await session.flush()
        source = Source(notebook_id=notebook.id, kind="text", title="Delete me", config={})
        session.add(source)
        await session.flush()
        notebook_id, source_id = notebook.id, source.id
        await session.commit()

    try:
        await index_chunks(
            notebook_id=str(notebook_id),
            source_id=str(source_id),
            source_type="text",
            title="Delete me",
            chunks=[_chunk("alpha beta cleanup")],
            embeddings=embeddings,
        )

        async with async_session_factory() as session:
            loaded = await session.get(Source, source_id)
            assert loaded is not None
            await source_service.delete(session, loaded)

        results = await search_chunks(
            str(notebook_id),
            "alpha beta",
            k=10,
            embeddings=embeddings,
        )
        assert results == []
    finally:
        await delete_source(str(source_id))
        async with async_session_factory() as session:
            notebook = await session.get(Notebook, notebook_id)
            if notebook is not None:
                await session.delete(notebook)
                await session.commit()

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select

from app.db import async_session_factory
from app.models import Notebook, Source, SourceContent, SourceFile
from app.services.ingestion import worker
from app.services.vector_store import delete_source, search_chunks
from tests.helpers import FakeEmbeddings
from tests.pdf_fixture import make_pdf


@pytest.fixture
async def notebook_id() -> AsyncIterator[uuid.UUID]:
    async with async_session_factory() as session:
        notebook = Notebook(name="Worker tests")
        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)
        notebook_id = notebook.id

    yield notebook_id

    # Remove vectors before the notebook cascades its source rows away.
    async with async_session_factory() as session:
        source_ids = list(
            await session.scalars(select(Source.id).where(Source.notebook_id == notebook_id))
        )
    for source_id in source_ids:
        await delete_source(str(source_id))

    async with async_session_factory() as session:
        notebook = await session.get(Notebook, notebook_id)
        if notebook is not None:
            await session.delete(notebook)
            await session.commit()


async def _create_source(
    notebook_id: uuid.UUID,
    *,
    text: str = "hello",
    status: str = "queued",
    with_content: bool = True,
) -> uuid.UUID:
    async with async_session_factory() as session:
        source = Source(
            notebook_id=notebook_id,
            kind="text",
            title="Worker test",
            status=status,
            stage="embedding" if status == "processing" else None,
        )
        session.add(source)
        await session.flush()
        if with_content:
            session.add(SourceContent(source_id=source.id, text=text))
        await session.commit()
        return source.id


async def test_process_next_marks_text_source_ready(notebook_id: uuid.UUID) -> None:
    source_id = await _create_source(notebook_id, text="Hello worker")

    assert await worker.process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "ready"
        assert source.stage is None
        assert source.error is None
        assert source.char_count == len("Hello worker")
        assert source.chunk_count == 1


async def test_requeue_recovers_interrupted_source(notebook_id: uuid.UUID) -> None:
    source_id = await _create_source(notebook_id, status="processing")

    async with async_session_factory() as session:
        assert await worker.requeue_stale(session) >= 1
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "queued"
        assert source.stage is None

    assert await worker.process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "ready"


async def test_claim_skips_locked_rows(notebook_id: uuid.UUID) -> None:
    source_id = await _create_source(notebook_id)

    async with async_session_factory() as locker, async_session_factory() as claimant:
        locked = await locker.scalar(select(Source).where(Source.id == source_id).with_for_update())
        assert locked is not None
        # The only queued row is locked, so a second claim must find nothing.
        assert await worker.claim_next(claimant) is None
        await locker.rollback()

    async with async_session_factory() as session:
        assert await worker.claim_next(session) == source_id


async def test_concurrent_claims_are_distinct(notebook_id: uuid.UUID) -> None:
    first = await _create_source(notebook_id)
    await asyncio.sleep(0.01)
    second = await _create_source(notebook_id)

    async with async_session_factory() as s1, async_session_factory() as s2:
        claimed = await asyncio.gather(worker.claim_next(s1), worker.claim_next(s2))

    assert set(claimed) == {first, second}


async def test_failure_marks_source_failed(notebook_id: uuid.UUID) -> None:
    source_id = await _create_source(notebook_id, with_content=False)

    assert await worker.process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "failed"
        assert source.stage is None
        assert source.error is not None
        assert "No text content" in source.error


async def test_pipeline_indexes_searchable_chunks(notebook_id: uuid.UUID) -> None:
    source_id = await _create_source(notebook_id, text="alpha beta gamma delta")
    embeddings = FakeEmbeddings()

    try:
        assert await worker.process_next(embeddings=embeddings) is True

        results = await search_chunks(
            str(notebook_id),
            "alpha beta",
            k=5,
            embeddings=embeddings,
        )
        assert any(document.metadata["source_id"] == str(source_id) for document, _ in results)
    finally:
        await delete_source(str(source_id))


async def _create_pdf_source(notebook_id: uuid.UUID, *, data: bytes | None = None) -> uuid.UUID:
    file_bytes = data if data is not None else make_pdf(["alpha beta", "gamma delta"])
    async with async_session_factory() as session:
        source = Source(
            notebook_id=notebook_id,
            kind="pdf",
            title="PDF worker test",
            config={"filename": "test.pdf", "size_bytes": len(file_bytes)},
        )
        session.add(source)
        await session.flush()
        session.add(
            SourceFile(
                source_id=source.id,
                filename="test.pdf",
                content_type="application/pdf",
                size_bytes=len(file_bytes),
                file_bytes=file_bytes,
            )
        )
        await session.commit()
        return source.id


async def test_pdf_pipeline_keeps_page_metadata(notebook_id: uuid.UUID) -> None:
    source_id = await _create_pdf_source(notebook_id)
    embeddings = FakeEmbeddings()

    try:
        assert await worker.process_next(embeddings=embeddings) is True

        async with async_session_factory() as session:
            source = await session.get(Source, source_id)
            assert source is not None
            assert source.status == "ready"
            assert source.chunk_count == 2
            assert source.char_count == len("alpha beta\n\ngamma delta")

            content = await session.get(SourceContent, source_id)
            assert content is not None
            assert content.text is None
            assert content.pages is not None
            assert [page["page"] for page in content.pages] == [1, 2]

        results = await search_chunks(str(notebook_id), "alpha gamma", k=5, embeddings=embeddings)
        pages = {
            document.metadata["page"]
            for document, _ in results
            if document.metadata["source_id"] == str(source_id)
        }
        assert pages == {1, 2}
    finally:
        await delete_source(str(source_id))


async def test_corrupt_pdf_marks_source_failed(notebook_id: uuid.UUID) -> None:
    source_id = await _create_pdf_source(notebook_id, data=b"not a pdf")

    assert await worker.process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "failed"
        assert source.stage is None
        assert source.error is not None
        assert "Could not read PDF" in source.error

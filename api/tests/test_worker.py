import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select

from app.db import async_session_factory
from app.models import Notebook, Source, SourceContent
from app.services.ingestion import worker


@pytest.fixture
async def notebook_id() -> AsyncIterator[uuid.UUID]:
    async with async_session_factory() as session:
        notebook = Notebook(name="Worker tests")
        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)
        notebook_id = notebook.id

    yield notebook_id

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

    assert await worker.process_next() is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "ready"
        assert source.stage is None
        assert source.error is None
        assert source.char_count == len("Hello worker")
        assert source.chunk_count is None


async def test_requeue_recovers_interrupted_source(notebook_id: uuid.UUID) -> None:
    source_id = await _create_source(notebook_id, status="processing")

    async with async_session_factory() as session:
        assert await worker.requeue_stale(session) >= 1
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "queued"
        assert source.stage is None

    assert await worker.process_next() is True

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

    assert await worker.process_next() is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "failed"
        assert source.stage is None
        assert source.error is not None
        assert "No text content" in source.error

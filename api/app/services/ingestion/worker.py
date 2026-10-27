"""Postgres-backed ingestion worker (P2.1 skeleton).

The `sources` table is the queue. A claim takes one row with
FOR UPDATE SKIP LOCKED, flips it to `processing`, and commits; that releases
the lock while keeping the row invisible to other workers. Startup requeues
rows left in `processing` by a crash.

P2.1 processes text only. The stub advances stages and marks the source ready;
P2.2 replaces it with extract -> chunk -> embed+index.
"""

import asyncio
import logging
import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.models import Source, SourceContent

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
MAX_ERROR_LENGTH = 1000


class IngestionError(Exception):
    """A source-specific failure that is safe to show in `sources.error`."""


async def requeue_stale(session: AsyncSession) -> int:
    """Reset interrupted `processing` rows to `queued`; return the count."""
    result = await session.execute(
        update(Source)
        .where(Source.status == "processing")
        .values(status="queued", stage=None, error=None, updated_at=func.now())
    )
    await session.commit()
    return cast("CursorResult[Any]", result).rowcount or 0


async def claim_next(session: AsyncSession) -> uuid.UUID | None:
    """Atomically claim the oldest queued source, or return None."""
    source = await session.scalar(
        select(Source)
        .where(Source.status == "queued")
        .order_by(Source.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if source is None:
        await session.rollback()
        return None

    source.status = "processing"
    source.stage = "extracting"
    source.error = None
    await session.commit()
    logger.info("claimed source %s", source.id)
    return source.id


async def _advance(session: AsyncSession, source: Source, stage: str) -> None:
    """Persist a stage transition so polling clients can see progress."""
    source.stage = stage
    await session.commit()


async def _run_text_stub(session: AsyncSession, source: Source) -> None:
    """Stand-in pipeline: validate the snapshot and walk the status machine."""
    content = await session.get(SourceContent, source.id)
    if content is None or not content.text:
        raise IngestionError("No text content to ingest")

    source.char_count = len(content.text)
    await _advance(session, source, "chunking")
    await _advance(session, source, "embedding")
    await _advance(session, source, "indexing")

    source.status = "ready"
    source.stage = None
    source.error = None
    await session.commit()


async def process_next() -> bool:
    """Claim and process one queued source; True when a row was handled."""
    async with async_session_factory() as session:
        source_id = await claim_next(session)
    if source_id is None:
        return False

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            return True

        try:
            await _run_text_stub(session, source)
        except Exception as exc:  # worker boundary: never kill the loop
            logger.exception("source %s failed", source_id)
            await session.rollback()
            failed = await session.get(Source, source_id)
            if failed is not None:
                failed.status = "failed"
                failed.stage = None
                failed.error = (str(exc) or "Ingestion failed")[:MAX_ERROR_LENGTH]
                await session.commit()
        else:
            logger.info("source %s ready", source_id)

    return True


async def run_worker() -> None:
    """Poll for queued sources until the task is cancelled."""
    while True:
        try:
            handled = await process_next()
        except Exception:  # a transient DB/network error must not stop the loop
            logger.exception("worker iteration failed")
            handled = False

        if not handled:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def startup() -> None:
    """Recover jobs interrupted by the previous process before polling."""
    async with async_session_factory() as session:
        count = await requeue_stale(session)
    if count:
        logger.warning("requeued %d interrupted source(s)", count)

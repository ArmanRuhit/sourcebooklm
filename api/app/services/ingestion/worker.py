"""Postgres-backed ingestion worker (P2.2).

The `sources` table is the queue. A claim takes one row with
FOR UPDATE SKIP LOCKED, flips it to `processing`, and commits; that releases
the lock while keeping the row invisible to other workers. Startup requeues
rows left in `processing` by a crash.

P2.2 runs the LangGraph pipeline for text sources: extract -> chunk ->
embed and index. Later phases add extractors for the other source kinds.
"""

import asyncio
import logging
import uuid
from typing import Any, cast

from langchain_core.embeddings import Embeddings
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.models import Source
from app.services import vector_store
from app.services.ingestion import graph

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
MAX_ERROR_LENGTH = 1000


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


async def _mark_failed(source_id: uuid.UUID, exc: Exception) -> None:
    """Remove partial vectors, then record a user-safe failure message."""
    try:
        await vector_store.delete_source(str(source_id))
    except Exception:  # cleanup is best-effort; never mask the real error
        logger.warning("could not remove partial vectors for %s", source_id, exc_info=True)

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            return

        source.status = "failed"
        source.stage = None
        source.error = (str(exc) or "Ingestion failed")[:MAX_ERROR_LENGTH]
        await session.commit()


async def process_next(embeddings: Embeddings | None = None) -> bool:
    """Claim and process one queued source; True when a row was handled."""
    async with async_session_factory() as session:
        source_id = await claim_next(session)
    if source_id is None:
        return False

    async with async_session_factory() as session:
        if await session.get(Source, source_id) is None:
            return True

    try:
        await graph.run_ingestion(source_id, embeddings=embeddings)
    except Exception as exc:  # worker boundary: never kill the loop
        logger.exception("source %s failed", source_id)
        await _mark_failed(source_id, exc)
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

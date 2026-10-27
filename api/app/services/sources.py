"""Source service - database operations with no HTTP concerns."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source, SourceContent
from app.schemas import SourceCreate
from app.services import vector_store


def _title_from_text(text: str) -> str:
    """Use the first non-empty line as a fallback title."""
    for line in text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:200]
    return "Untitled source"


async def create(session: AsyncSession, notebook_id: uuid.UUID, data: SourceCreate) -> Source:
    """Insert a queued source plus its extracted-text snapshot."""
    source = Source(
        notebook_id=notebook_id,
        kind=data.kind,
        title=data.title or _title_from_text(data.text),
        config={},
    )
    session.add(source)
    await session.flush()  # assign source.id before inserting the content row

    session.add(SourceContent(source_id=source.id, text=data.text))
    await session.commit()
    await session.refresh(source)
    return source


async def list_for_notebook(session: AsyncSession, notebook_id: uuid.UUID) -> list[Source]:
    """Return a notebook's sources, newest first."""
    result = await session.scalars(
        select(Source).where(Source.notebook_id == notebook_id).order_by(Source.created_at.desc())
    )
    return list(result)


async def get(session: AsyncSession, source_id: uuid.UUID) -> Source | None:
    return await session.get(Source, source_id)


async def delete(session: AsyncSession, source: Source) -> None:
    """Delete a source; vectors and files/contents cascade from here."""
    await vector_store.delete_source(str(source.id))
    await session.delete(source)
    await session.commit()

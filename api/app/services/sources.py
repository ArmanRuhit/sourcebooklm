"""Source service - database operations with no HTTP concerns."""

import uuid
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source, SourceContent, SourceFile
from app.schemas import SourceCreate
from app.services import vector_store


def _title_from_text(text: str) -> str:
    """Use the first non-empty line as a fallback title."""
    for line in text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:200]
    return "Untitled source"


def _title_from_filename(filename: str) -> str:
    """Use the filename stem as a fallback title."""
    stem = Path(filename).stem.strip()
    return stem[:200] if stem else "Untitled source"


def _title_from_url(url: str) -> str:
    """Use the hostname as a placeholder until the page title is fetched."""
    host = (urlsplit(url).hostname or url).removeprefix("www.")
    return host[:200] or "Untitled source"


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


async def create_url(
    session: AsyncSession,
    notebook_id: uuid.UUID,
    *,
    url: str,
    title: str | None = None,
) -> Source:
    """Insert a queued website source; the worker fetches and fills its text."""
    source = Source(
        notebook_id=notebook_id,
        kind="url",
        title=title or _title_from_url(url),
        config={"url": url, "custom_title": title is not None},
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def create_youtube(
    session: AsyncSession,
    notebook_id: uuid.UUID,
    *,
    video_id: str,
    url: str,
    title: str | None = None,
) -> Source:
    """Insert a queued YouTube source; the worker fetches its transcript."""
    source = Source(
        notebook_id=notebook_id,
        kind="youtube",
        title=title or "YouTube video",
        config={
            "url": url,
            "video_id": video_id,
            "custom_title": title is not None,
        },
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def create_pdf(
    session: AsyncSession,
    notebook_id: uuid.UUID,
    *,
    filename: str,
    data: bytes,
    title: str | None = None,
) -> Source:
    """Insert a queued PDF source plus its original bytes."""
    source = Source(
        notebook_id=notebook_id,
        kind="pdf",
        title=title or _title_from_filename(filename),
        config={"filename": filename, "size_bytes": len(data)},
    )
    session.add(source)
    await session.flush()

    session.add(
        SourceFile(
            source_id=source.id,
            filename=filename,
            content_type="application/pdf",
            size_bytes=len(data),
            file_bytes=data,
        )
    )
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

"""Source endpoints - HTTP shape only; logic lives in the service layer."""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.config import settings
from app.models import Source, SourceContent, SourceFile
from app.routers.deps import NotebookDep, SessionDep
from app.schemas import (
    SourceContentRead,
    SourceCreate,
    SourceRead,
    SourceUrlCreate,
    SourceYoutubeCreate,
)
from app.services import sources
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.web import extract_video_id

notebook_sources_router = APIRouter(prefix="/notebooks", tags=["sources"])
sources_router = APIRouter(prefix="/sources", tags=["sources"])

PDF_MAGIC = b"%PDF-"
MAX_FILENAME_LENGTH = 255
STREAM_CHUNK_SIZE = 64 * 1024


async def _get_source_or_404(session: SessionDep, source_id: uuid.UUID) -> Source:
    """Fetch a source or raise 404."""
    source = await sources.get(session, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


def _clean_title(title: str | None) -> str | None:
    """Normalize the optional title and enforce the database bound."""
    cleaned = (title or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Title must be 200 characters or fewer",
        )
    return cleaned


def _iter_bytes(data: bytes) -> Iterator[bytes]:
    for start in range(0, len(data), STREAM_CHUNK_SIZE):
        yield data[start : start + STREAM_CHUNK_SIZE]


@notebook_sources_router.get("/{notebook_id}/sources", response_model=list[SourceRead])
async def list_sources(notebook: NotebookDep, session: SessionDep) -> list[Source]:
    """List a notebook's sources, newest first."""
    return await sources.list_for_notebook(session, notebook.id)


@notebook_sources_router.post(
    "/{notebook_id}/sources",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    notebook: NotebookDep,
    session: SessionDep,
    kind: Annotated[Literal["text", "pdf", "url", "youtube"], Form()],
    title: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
    url: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> Source:
    """Add a text, PDF, or website source; the worker picks it up from the queue."""
    if kind == "text":
        if file is not None and file.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Files are only supported for PDF sources",
            )
        try:
            payload = SourceCreate(kind="text", title=title, text=text or "")
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        return await sources.create(session, notebook.id, payload)

    if kind == "url":
        if file is not None and file.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Files are only supported for PDF sources",
            )
        try:
            url_payload = SourceUrlCreate.model_validate(
                {"kind": "url", "title": title, "url": url or ""}
            )
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        return await sources.create_url(
            session,
            notebook.id,
            url=str(url_payload.url),
            title=url_payload.title,
        )

    if kind == "youtube":
        if file is not None and file.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Files are only supported for PDF sources",
            )
        try:
            youtube_payload = SourceYoutubeCreate.model_validate(
                {"kind": "youtube", "title": title, "url": url or ""}
            )
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        try:
            video_id = extract_video_id(str(youtube_payload.url))
        except IngestionError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return await sources.create_youtube(
            session,
            notebook.id,
            video_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=youtube_payload.title,
        )

    if file is None or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A PDF file is required",
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"PDF must be {settings.max_upload_mb} MB or smaller",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded PDF is empty",
        )
    if PDF_MAGIC not in data[:1024]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File must be a PDF",
        )

    filename = Path(file.filename).name[-MAX_FILENAME_LENGTH:] or "document.pdf"
    return await sources.create_pdf(
        session,
        notebook.id,
        filename=filename,
        data=data,
        title=_clean_title(title),
    )


@sources_router.get("/{source_id}", response_model=SourceRead)
async def get_source(source_id: uuid.UUID, session: SessionDep) -> Source:
    """Get one source."""
    return await _get_source_or_404(session, source_id)


@sources_router.get("/{source_id}/content", response_model=SourceContentRead)
async def get_source_content(source_id: uuid.UUID, session: SessionDep) -> SourceContent:
    """Return the stored text snapshot for the source viewer."""
    await _get_source_or_404(session, source_id)
    content = await session.get(SourceContent, source_id)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source content not found",
        )
    return content


@sources_router.get("/{source_id}/file")
async def get_source_file(source_id: uuid.UUID, session: SessionDep) -> StreamingResponse:
    """Stream the original uploaded PDF."""
    uploaded = await session.get(SourceFile, source_id)
    if uploaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found")

    return StreamingResponse(
        _iter_bytes(uploaded.file_bytes),
        media_type=uploaded.content_type,
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{quote(uploaded.filename, safe='')}"
            ),
            "Content-Length": str(uploaded.size_bytes),
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@sources_router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: uuid.UUID, session: SessionDep) -> None:
    """Delete a source and everything derived from it."""
    source = await _get_source_or_404(session, source_id)
    await sources.delete(session, source)

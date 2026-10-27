"""Source endpoints - HTTP shape only; logic lives in the service layer."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, status

from app.models import Source
from app.routers.deps import NotebookDep, SessionDep
from app.schemas import SourceCreate, SourceRead
from app.services import sources

notebook_sources_router = APIRouter(prefix="/notebooks", tags=["sources"])
sources_router = APIRouter(prefix="/sources", tags=["sources"])


async def _get_source_or_404(session: SessionDep, source_id: uuid.UUID) -> Source:
    """Fetch a source or raise 404."""
    source = await sources.get(session, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


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
    payload: Annotated[SourceCreate, Form()],
) -> Source:
    """Add a text source; the worker picks it up from the queue."""
    return await sources.create(session, notebook.id, payload)


@sources_router.get("/{source_id}", response_model=SourceRead)
async def get_source(source_id: uuid.UUID, session: SessionDep) -> Source:
    """Get one source."""
    return await _get_source_or_404(session, source_id)


@sources_router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: uuid.UUID, session: SessionDep) -> None:
    """Delete a source and everything derived from it."""
    source = await _get_source_or_404(session, source_id)
    await sources.delete(session, source)

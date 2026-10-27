"""Notebook endpoints - HTTP shape only; logic lives in the service layer."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Notebook
from app.schemas import NotebookCreate, NotebookRead, NotebookUpdate
from app.services import notebooks

router = APIRouter(prefix="/notebooks", tags=["notebooks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _get_or_404(session: AsyncSession, notebook_id: uuid.UUID) -> Notebook:
    """Fetch a notebook or raise 404"""
    notebook = await notebooks.get(session, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    return notebook


@router.post("", response_model=NotebookRead, status_code=status.HTTP_201_CREATED)
async def create_notebook(payload: NotebookCreate, session: SessionDep) -> Notebook:
    """Create a notebook."""
    return await notebooks.create(session, payload)


@router.get("", response_model=list[NotebookRead])
async def list_notebooks(session: SessionDep) -> list[Notebook]:
    """List all notebooks."""
    return await notebooks.list_all(session)


@router.get("/{notebook_id}", response_model=NotebookRead)
async def get_notebook(notebook_id: uuid.UUID, session: SessionDep) -> Notebook:
    """Get one notebook."""
    return await _get_or_404(session, notebook_id)


@router.patch("/{notebook_id}", response_model=NotebookRead)
async def rename_notebook(
    notebook_id: uuid.UUID, payload: NotebookUpdate, session: SessionDep
) -> Notebook:
    """Rename a notebook."""
    notebook = await _get_or_404(session, notebook_id)
    return await notebooks.rename(session, notebook, payload)


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(notebook_id: uuid.UUID, session: SessionDep) -> None:
    """Delete a notebook and everything inside it."""
    notebook = await _get_or_404(session, notebook_id)
    await notebooks.delete(session, notebook)

"""Notebook service - database operations with no HTTP concerns."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notebook
from app.schemas import NotebookCreate, NotebookUpdate


async def create(session: AsyncSession, data: NotebookCreate) -> Notebook:
    """Insert a notebook and return it with server defaults applied."""
    notebook = Notebook(name=data.name)
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)
    return notebook


async def list_all(session: AsyncSession) -> list[Notebook]:
    """Return every notebook, most recently updated first"""
    result = await session.scalars(select(Notebook).order_by(Notebook.updated_at.desc()))
    return list(result)


async def get(session: AsyncSession, notebook_id: uuid.UUID) -> Notebook | None:
    return await session.get(Notebook, notebook_id)


async def rename(session: AsyncSession, notebook: Notebook, data: NotebookUpdate) -> Notebook:
    """Apply a new name and return the refreshed notebook."""
    notebook.name = data.name
    await session.commit()
    await session.refresh(notebook)
    return notebook


async def delete(session: AsyncSession, notebook: Notebook) -> None:
    """Delete a notebook; child rows go with it via ON DELETE CASCADE"""
    await session.delete(notebook)
    await session.commit()

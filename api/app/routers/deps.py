"""Shared router dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Notebook
from app.services import notebooks

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_notebook_or_404(notebook_id: uuid.UUID, session: SessionDep) -> Notebook:
    """Resolve the path's notebook_id or raise a 404."""
    notebook = await notebooks.get(session, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    return notebook


NotebookDep = Annotated[Notebook, Depends(get_notebook_or_404)]

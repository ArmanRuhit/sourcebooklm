"""Notebook endpoints - HTTP shape only; logic lives in the service layer."""

from fastapi import APIRouter, status

from app.models import Notebook
from app.routers.deps import NotebookDep, SessionDep
from app.schemas import NotebookCreate, NotebookRead, NotebookUpdate
from app.services import notebooks

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.post("", response_model=NotebookRead, status_code=status.HTTP_201_CREATED)
async def create_notebook(payload: NotebookCreate, session: SessionDep) -> Notebook:
    """Create a notebook."""
    return await notebooks.create(session, payload)


@router.get("", response_model=list[NotebookRead])
async def list_notebooks(session: SessionDep) -> list[Notebook]:
    """List all notebooks."""
    return await notebooks.list_all(session)


@router.get("/{notebook_id}", response_model=NotebookRead)
async def get_notebook(notebook: NotebookDep) -> Notebook:
    """Get one notebook."""
    return notebook


@router.patch("/{notebook_id}", response_model=NotebookRead)
async def rename_notebook(
    notebook: NotebookDep, payload: NotebookUpdate, session: SessionDep
) -> Notebook:
    """Rename a notebook."""
    return await notebooks.rename(session, notebook, payload)


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(notebook: NotebookDep, session: SessionDep) -> None:
    """Delete a notebook and everything inside it."""
    await notebooks.delete(session, notebook)

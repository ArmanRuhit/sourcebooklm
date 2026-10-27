"""Chat endpoints - streaming answers and persisted history."""

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from app.models import Message
from app.routers.deps import NotebookDep, SessionDep
from app.schemas import MessageRead, QueryRequest
from app.services.rag import chat

router = APIRouter(prefix="/notebooks", tags=["chat"])


@router.post("/{notebook_id}/query")
async def query_notebook(notebook: NotebookDep, payload: QueryRequest) -> EventSourceResponse:
    """Stream a grounded answer as Server-Sent Events."""
    return EventSourceResponse(
        chat.query_events(str(notebook.id), payload.question),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{notebook_id}/messages", response_model=list[MessageRead])
async def list_messages(notebook: NotebookDep, session: SessionDep) -> list[Message]:
    """Return the notebook's conversation history, oldest first."""
    return await chat.list_messages(session, notebook.id)

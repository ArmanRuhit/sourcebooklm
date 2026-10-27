"""Grounded answer orchestration: retrieve, prompt, stream, persist."""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.models import Conversation, Message
from app.services.rag import llm, retriever

logger = logging.getLogger(__name__)

NO_CONTEXT_ANSWER = (
    "I couldn't find anything in this notebook's sources to answer that question. "
    "Add a source, wait for it to finish indexing, or try rephrasing."
)
MAX_SNIPPET_LENGTH = 500

SYSTEM_PROMPT = """You are SourcebookLM, a research assistant that answers only from the
user's sources.

Rules:
- Use only the numbered context blocks in this request.
- Cite every factual claim with the matching block number, like [1] or [2][3].
- Never cite a number that is not in the context.
- If the context does not contain the answer, say you couldn't find it in the
  notebook's sources. Do not use outside knowledge.
- Be concise. Use Markdown when structure helps.
"""


def citation_from_document(index: int, document: Document) -> dict[str, Any]:
    """Convert a retrieved document into the citation snapshot persisted with a message."""
    metadata = document.metadata
    return {
        "index": index,
        "source_id": str(metadata.get("source_id", "")),
        "source_title": str(metadata.get("title") or "Untitled source"),
        "source_kind": str(metadata.get("source_type") or "text"),
        "chunk_index": metadata.get("chunk_index"),
        "page": metadata.get("page"),
        "start_seconds": metadata.get("start_seconds"),
        "end_seconds": metadata.get("end_seconds"),
        "char_start": metadata.get("char_start"),
        "char_end": metadata.get("char_end"),
        "snippet": document.page_content[:MAX_SNIPPET_LENGTH],
    }


def build_context(documents: list[Document]) -> str:
    """Render numbered context blocks for the prompt."""
    blocks: list[str] = []

    for index, document in enumerate(documents, start=1):
        metadata = document.metadata
        location = ""
        if metadata.get("page") is not None:
            location = f", page {metadata['page']}"
        elif metadata.get("start_seconds") is not None:
            location = f", starts at {metadata['start_seconds']}s"

        title = metadata.get("title") or "Untitled source"
        source_type = metadata.get("source_type") or "text"
        blocks.append(f"[{index}] {title} ({source_type}{location})\n{document.page_content}")

    return "\n\n".join(blocks)


def build_messages(question: str, documents: list[Document]) -> list[SystemMessage | HumanMessage]:
    """Build the grounded prompt. Retrieval has already guaranteed a non-empty context."""
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"Context:\n{build_context(documents)}\n\nQuestion: {question}",
        ),
    ]


def _chunk_text(chunk: Any) -> str:
    """Normalize LangChain streaming chunks (string or content blocks) to text."""
    content = getattr(chunk, "content", "")

    if isinstance(content, str):
        return content

    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    return "".join(parts)


def sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    """One Server-Sent Event payload."""
    return {"event": event, "data": json.dumps(data)}


async def get_or_create_conversation(session: AsyncSession, notebook_id: uuid.UUID) -> Conversation:
    """One rolling conversation per notebook (P3.5)."""
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.notebook_id == notebook_id)
        .order_by(Conversation.created_at)
        .limit(1)
    )

    if conversation is None:
        conversation = Conversation(notebook_id=notebook_id)
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

    return conversation


async def _add_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    *,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations,
        model=model,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def list_messages(session: AsyncSession, notebook_id: uuid.UUID) -> list[Message]:
    """Return the notebook's conversation history, oldest first."""
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.notebook_id == notebook_id)
        .order_by(Conversation.created_at)
        .limit(1)
    )

    if conversation is None:
        return []

    return list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    )


async def query_events(notebook_id: str, question: str) -> AsyncIterator[dict[str, str]]:
    """Yield the SSE sequence: meta, citations, token*, done | error."""
    notebook_uuid = uuid.UUID(notebook_id)

    async with async_session_factory() as session:
        conversation = await get_or_create_conversation(session, notebook_uuid)
        user_message = await _add_message(
            session,
            conversation.id,
            role="user",
            content=question,
        )

        citations: list[dict[str, Any]] = []
        answer = ""

        try:
            documents = await retriever.retrieve(notebook_id, question, use_rerank=True)
            citations = [
                citation_from_document(index, document)
                for index, document in enumerate(documents, start=1)
            ]

            yield sse(
                "meta",
                {
                    "conversation_id": str(conversation.id),
                    "user_message_id": str(user_message.id),
                    "citations": citations,
                },
            )
            yield sse("citations", {"citations": citations})

            if not citations:
                answer = NO_CONTEXT_ANSWER
                yield sse("token", {"text": answer})
                assistant = await _add_message(
                    session,
                    conversation.id,
                    role="assistant",
                    content=answer,
                    citations=[],
                    model=llm.model_name(),
                )
                yield sse(
                    "done",
                    {
                        "message_id": str(assistant.id),
                        "content": answer,
                        "citations": [],
                        "model": assistant.model,
                    },
                )
                return

            model = llm.get_chat_model()
            parts: list[str] = []

            async for chunk in model.astream(build_messages(question, documents)):
                text = _chunk_text(chunk)
                if text:
                    parts.append(text)
                    yield sse("token", {"text": text})

            answer = "".join(parts).strip()
            assistant = await _add_message(
                session,
                conversation.id,
                role="assistant",
                content=answer,
                citations=citations,
                model=llm.model_name(),
            )
            yield sse(
                "done",
                {
                    "message_id": str(assistant.id),
                    "content": answer,
                    "citations": citations,
                    "model": assistant.model,
                },
            )
        except Exception as exc:
            logger.exception("Query failed for notebook %s", notebook_id)
            if answer:
                await _add_message(
                    session,
                    conversation.id,
                    role="assistant",
                    content=answer,
                    citations=citations,
                    model=llm.model_name(),
                )
            yield sse(
                "error",
                {
                    "message": str(exc) or "The answer could not be generated.",
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )

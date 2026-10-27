"""Streaming query endpoint and persisted chat history."""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.documents import Document
from langchain_core.messages import AIMessageChunk

from app.main import app
from app.services.rag import chat


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id(client: AsyncClient) -> AsyncIterator[str]:
    created = await client.post("/api/v1/notebooks", json={"name": "Query tests"})
    assert created.status_code == 201
    notebook_id = created.json()["id"]
    yield notebook_id
    await client.delete(f"/api/v1/notebooks/{notebook_id}")


def parse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []

    for block in body.replace("\r\n", "\n").strip().split("\n\n"):
        event = ""
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        if event and data:
            events.append((event, json.loads(data)))

    return events


async def test_empty_notebook_refuses_without_calling_llm(
    client: AsyncClient,
    notebook_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def empty_retrieve(*args: object, **kwargs: object) -> list[Document]:
        return []

    monkeypatch.setattr(chat.retriever, "retrieve", empty_retrieve)

    response = await client.post(
        f"/api/v1/notebooks/{notebook_id}/query",
        json={"question": "What does the source say?"},
    )

    assert response.status_code == 200
    events = parse_events(response.text)
    assert [event for event, _ in events] == ["meta", "citations", "token", "done"]
    assert events[2][1]["text"] == chat.NO_CONTEXT_ANSWER
    assert events[1][1]["citations"] == []

    history = await client.get(f"/api/v1/notebooks/{notebook_id}/messages")
    assert history.status_code == 200
    messages = history.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "What does the source say?"
    assert messages[1]["content"] == chat.NO_CONTEXT_ANSWER
    assert messages[1]["citations"] == []


async def test_query_streams_cited_answer_and_persists_it(
    client: AsyncClient,
    notebook_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = Document(
        page_content="Chunk overlap preserves context across boundaries.",
        metadata={
            "notebook_id": notebook_id,
            "source_id": "44444444-4444-4444-4444-444444444444",
            "source_type": "pdf",
            "title": "RAG notes",
            "chunk_index": 0,
            "page": 2,
            "char_start": 0,
            "char_end": 53,
        },
    )

    async def fake_retrieve(*args: object, **kwargs: object) -> list[Document]:
        return [document]

    class FakeModel:
        async def astream(self, messages: object) -> AsyncIterator[AIMessageChunk]:
            for text in ["Overlap keeps ", "context intact [1]."]:
                yield AIMessageChunk(content=text)

    monkeypatch.setattr(chat.retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat.llm, "get_chat_model", lambda: FakeModel())

    response = await client.post(
        f"/api/v1/notebooks/{notebook_id}/query",
        json={"question": "Why does overlap matter?"},
    )

    assert response.status_code == 200
    events = parse_events(response.text)
    names = [event for event, _ in events]
    assert names[:2] == ["meta", "citations"]
    assert names[-1] == "done"
    assert "token" in names

    citations = events[1][1]["citations"]
    assert citations[0]["page"] == 2
    assert citations[0]["source_title"] == "RAG notes"
    assert citations[0]["source_kind"] == "pdf"

    tokens = "".join(data["text"] for event, data in events if event == "token")
    assert tokens == "Overlap keeps context intact [1]."
    assert events[-1][1]["content"] == tokens

    history = await client.get(f"/api/v1/notebooks/{notebook_id}/messages")
    messages = history.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["citations"][0]["source_id"] == "44444444-4444-4444-4444-444444444444"


async def test_blank_question_is_rejected(client: AsyncClient, notebook_id: str) -> None:
    response = await client.post(
        f"/api/v1/notebooks/{notebook_id}/query",
        json={"question": "   "},
    )
    assert response.status_code == 422


async def test_unknown_notebook_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/notebooks/00000000-0000-0000-0000-000000000000/query",
        json={"question": "Anything?"},
    )
    assert response.status_code == 404

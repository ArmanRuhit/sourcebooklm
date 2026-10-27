"""Retriever: notebook filtering and MMR selection."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.ingestion.chunker import Chunk
from app.services.rag.retriever import retrieve
from app.services.vector_store import delete_source, index_chunks
from tests.helpers import FakeEmbeddings


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id(client: AsyncClient) -> AsyncIterator[str]:
    created = await client.post("/api/v1/notebooks", json={"name": "Retriever tests"})
    assert created.status_code == 201
    notebook_id = created.json()["id"]
    yield notebook_id
    await client.delete(f"/api/v1/notebooks/{notebook_id}")


def _chunk(text: str, index: int = 0) -> Chunk:
    return Chunk(text=text, index=index, char_start=0, char_end=len(text))


async def test_retrieve_returns_relevant_chunk(notebook_id: str) -> None:
    embeddings = FakeEmbeddings()
    source_id = "11111111-1111-1111-1111-111111111111"
    await index_chunks(
        notebook_id=notebook_id,
        source_id=source_id,
        source_type="text",
        title="Neuroscience notes",
        chunks=[
            _chunk("Dopamine is a reward signal that shapes learning.", 0),
            _chunk("Pasta should be boiled in heavily salted water.", 1),
            _chunk("Dopamine receptors in the brain respond to prediction errors.", 2),
        ],
        embeddings=embeddings,
    )

    try:
        results = await retrieve(notebook_id, "dopamine reward learning", embeddings=embeddings)

        assert results
        assert "dopamine" in results[0].page_content.lower()
        assert len(results) <= 6
    finally:
        await delete_source(source_id)


async def test_retrieve_never_returns_another_notebooks_chunks(
    client: AsyncClient,
) -> None:
    embeddings = FakeEmbeddings()
    first = await client.post("/api/v1/notebooks", json={"name": "First"})
    second = await client.post("/api/v1/notebooks", json={"name": "Second"})
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    a_source = "22222222-2222-2222-2222-222222222222"
    b_source = "33333333-3333-3333-3333-333333333333"

    try:
        await index_chunks(
            notebook_id=first_id,
            source_id=a_source,
            source_type="text",
            title="Alpha",
            chunks=[_chunk("Alpha notebook discusses gardens and sunlight.")],
            embeddings=embeddings,
        )
        await index_chunks(
            notebook_id=second_id,
            source_id=b_source,
            source_type="text",
            title="Beta",
            chunks=[_chunk("Quantum zebras orbit the moon during eclipses.")],
            embeddings=embeddings,
        )

        results = await retrieve(first_id, "quantum zebras eclipses", embeddings=embeddings)

        assert all(document.metadata["notebook_id"] == first_id for document in results)
        assert all(document.metadata["source_id"] != b_source for document in results)
    finally:
        await delete_source(a_source)
        await delete_source(b_source)
        await client.delete(f"/api/v1/notebooks/{first_id}")
        await client.delete(f"/api/v1/notebooks/{second_id}")


async def test_blank_query_returns_nothing(notebook_id: str) -> None:
    assert await retrieve(notebook_id, "   ", embeddings=FakeEmbeddings()) == []

"""Source lifecycle: delete, re-index, and retry after a failure."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session_factory
from app.main import app
from app.services.ingestion import graph
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.web import Article
from app.services.ingestion.worker import claim_next, process_next
from app.services.vector_store import search_chunks
from tests.helpers import FakeEmbeddings


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id(client: AsyncClient) -> AsyncIterator[str]:
    created = await client.post("/api/v1/notebooks", json={"name": "Lifecycle tests"})
    assert created.status_code == 201
    notebook_id = created.json()["id"]
    yield notebook_id
    await client.delete(f"/api/v1/notebooks/{notebook_id}")


async def _create_text_source(client: AsyncClient, notebook_id: str) -> str:
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "text", "title": "Retry me", "text": "alpha beta gamma delta"},
    )
    assert created.status_code == 201
    return created.json()["id"]


async def test_reindex_twice_rebuilds_without_duplicate_vectors(
    client: AsyncClient, notebook_id: str
) -> None:
    embeddings = FakeEmbeddings()
    source_id = await _create_text_source(client, notebook_id)

    assert await process_next(embeddings) is True

    ready = await client.get(f"/api/v1/sources/{source_id}")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["chunk_count"] == 1
    assert await search_chunks(notebook_id, "alpha beta", k=10, embeddings=embeddings)

    for _ in range(2):
        queued = await client.post(f"/api/v1/sources/{source_id}/reindex")
        assert queued.status_code == 202
        payload = queued.json()
        assert payload["status"] == "queued"
        assert payload["stage"] is None
        assert payload["error"] is None
        assert payload["chunk_count"] == 0

    assert await search_chunks(notebook_id, "alpha beta", k=10, embeddings=embeddings) == []

    assert await process_next(embeddings) is True
    results = await search_chunks(notebook_id, "alpha beta", k=10, embeddings=embeddings)
    matching = [document for document, _ in results if document.metadata["source_id"] == source_id]
    assert len(matching) == 1
    assert len({document.metadata["chunk_index"] for document in matching}) == 1


async def test_delete_endpoint_removes_vectors(client: AsyncClient, notebook_id: str) -> None:
    embeddings = FakeEmbeddings()
    source_id = await _create_text_source(client, notebook_id)
    assert await process_next(embeddings) is True
    assert await search_chunks(notebook_id, "alpha beta", k=10, embeddings=embeddings)

    deleted = await client.delete(f"/api/v1/sources/{source_id}")
    assert deleted.status_code == 204

    assert await search_chunks(notebook_id, "alpha beta", k=10, embeddings=embeddings) == []
    assert (await client.get(f"/api/v1/sources/{source_id}")).status_code == 404


async def test_reindex_rejects_a_processing_source(client: AsyncClient, notebook_id: str) -> None:
    source_id = await _create_text_source(client, notebook_id)
    async with async_session_factory() as session:
        claimed = await claim_next(session)
    assert claimed is not None
    assert str(claimed) == source_id

    response = await client.post(f"/api/v1/sources/{source_id}/reindex")
    assert response.status_code == 409
    assert response.json() == {"detail": "Source is already being processed"}


async def test_failed_source_retries_after_the_underlying_fix(
    client: AsyncClient, notebook_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "url", "url": "https://example.com/fix-me"},
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    article = Article(
        url="https://example.com/fixed",
        title="Fixed article",
        description=None,
        text="The fixed article is readable now.",
    )
    calls = 0

    def flaky_fetch(url: str) -> Article:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise IngestionError("Could not fetch that URL")
        return article

    monkeypatch.setattr(graph, "fetch_article", flaky_fetch)

    assert await process_next(FakeEmbeddings()) is True
    failed = await client.get(f"/api/v1/sources/{source_id}")
    assert failed.json()["status"] == "failed"
    assert failed.json()["error"] == "Could not fetch that URL"

    retried = await client.post(f"/api/v1/sources/{source_id}/reindex")
    assert retried.status_code == 202
    assert retried.json()["status"] == "queued"
    assert retried.json()["error"] is None

    assert await process_next(FakeEmbeddings()) is True
    recovered = await client.get(f"/api/v1/sources/{source_id}")
    assert recovered.json()["status"] == "ready"
    assert recovered.json()["error"] is None
    assert recovered.json()["chunk_count"] == 1


async def test_reindex_missing_source_is_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/sources/00000000-0000-0000-0000-000000000000/reindex")
    assert response.status_code == 404
    assert response.json() == {"detail": "Source not found"}

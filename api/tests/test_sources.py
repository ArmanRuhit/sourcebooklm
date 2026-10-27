import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id(client: AsyncClient) -> AsyncIterator[str]:
    created = await client.post("/api/v1/notebooks", json={"name": "Source tests"})
    assert created.status_code == 201
    notebook_id = created.json()["id"]
    yield notebook_id
    await client.delete(f"/api/v1/notebooks/{notebook_id}")


async def test_source_crud(client: AsyncClient, notebook_id: str) -> None:
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "text", "title": "  Notes  ", "text": "  Hello world\nSecond line  "},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["title"] == "Notes"
    assert payload["kind"] == "text"
    assert payload["status"] == "queued"
    assert payload["stage"] is None
    assert payload["error"] is None
    assert payload["char_count"] is None
    source_id = payload["id"]

    listed = await client.get(f"/api/v1/notebooks/{notebook_id}/sources")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [source_id]

    fetched = await client.get(f"/api/v1/sources/{source_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Notes"

    deleted = await client.delete(f"/api/v1/sources/{source_id}")
    assert deleted.status_code == 204
    gone = await client.get(f"/api/v1/sources/{source_id}")
    assert gone.status_code == 404
    assert gone.json() == {"detail": "Source not found"}


async def test_title_falls_back_to_first_line(client: AsyncClient, notebook_id: str) -> None:
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "text", "text": "First line\nBody text"},
    )
    assert created.status_code == 201
    assert created.json()["title"] == "First line"


async def test_source_not_found(client: AsyncClient) -> None:
    missing_source = uuid.uuid4()
    assert (await client.get(f"/api/v1/sources/{missing_source}")).status_code == 404
    assert (await client.delete(f"/api/v1/sources/{missing_source}")).status_code == 404

    missing_notebook = uuid.uuid4()
    listed = await client.get(f"/api/v1/notebooks/{missing_notebook}/sources")
    assert listed.status_code == 404
    assert listed.json() == {"detail": "Notebook not found"}

    created = await client.post(
        f"/api/v1/notebooks/{missing_notebook}/sources",
        data={"kind": "text", "text": "hello"},
    )
    assert created.status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "text", "text": ""},
        {"kind": "text", "text": "   "},
        {"kind": "pdf", "text": "hello"},
        {"kind": "text", "title": "x" * 201, "text": "hello"},
    ],
)
async def test_invalid_source_rejected(
    client: AsyncClient, notebook_id: str, data: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data=data,
    )
    assert response.status_code == 422

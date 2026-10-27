import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session_factory
from app.main import app
from app.models import Source


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_notebook_crud(client: AsyncClient) -> None:
    created = await client.post("/api/v1/notebooks", json={"name": "  My notebook  "})
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "My notebook"
    notebook_id = payload["id"]

    listed = await client.get("/api/v1/notebooks")
    assert listed.status_code == 200
    assert notebook_id in [item["id"] for item in listed.json()]

    fetched = await client.get(f"/api/v1/notebooks/{notebook_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "My notebook"

    renamed = await client.patch(
        f"/api/v1/notebooks/{notebook_id}", json={"name": "Renamed notebook"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed notebook"

    deleted = await client.delete(f"/api/v1/notebooks/{notebook_id}")
    assert deleted.status_code == 204

    gone = await client.get(f"/api/v1/notebooks/{notebook_id}")
    assert gone.status_code == 404
    assert gone.json() == {"detail": "Notebook not found"}


async def test_notebook_not_found(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    responses = [
        await client.get(f"/api/v1/notebooks/{missing}"),
        await client.patch(f"/api/v1/notebooks/{missing}", json={"name": "x"}),
        await client.delete(f"/api/v1/notebooks/{missing}"),
    ]
    for response in responses:
        assert response.status_code == 404
        assert response.json() == {"detail": "Notebook not found"}


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_invalid_name_rejected(client: AsyncClient, name: str) -> None:
    response = await client.post("/api/v1/notebooks", json={"name": name})
    assert response.status_code == 422


async def test_name_length_boundary(client: AsyncClient) -> None:
    response = await client.post("/api/v1/notebooks", json={"name": "x" * 100})
    assert response.status_code == 201
    notebook_id = response.json()["id"]
    deleted = await client.delete(f"/api/v1/notebooks/{notebook_id}")
    assert deleted.status_code == 204


async def test_delete_notebook_cascades(client: AsyncClient) -> None:
    created = await client.post("/api/v1/notebooks", json={"name": "Cascade test"})
    notebook_id = uuid.UUID(created.json()["id"])

    async with async_session_factory() as session:
        source = Source(notebook_id=notebook_id, kind="text", title="temporary source")
        session.add(source)
        await session.commit()
        source_id = source.id

    deleted = await client.delete(f"/api/v1/notebooks/{notebook_id}")
    assert deleted.status_code == 204

    async with async_session_factory() as session:
        assert await session.get(Source, source_id) is None

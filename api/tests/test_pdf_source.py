"""PDF upload API: storage, validation, and original-file serving."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from tests.pdf_fixture import make_pdf


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id(client: AsyncClient) -> AsyncIterator[str]:
    created = await client.post("/api/v1/notebooks", json={"name": "PDF tests"})
    assert created.status_code == 201
    notebook_id = created.json()["id"]
    yield notebook_id
    await client.delete(f"/api/v1/notebooks/{notebook_id}")


async def test_upload_pdf_and_stream_original(client: AsyncClient, notebook_id: str) -> None:
    data = make_pdf(["First page", "Second page"])
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "pdf", "title": "  Course notes  "},
        files={"file": ("course notes.pdf", data, "application/pdf")},
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["kind"] == "pdf"
    assert payload["title"] == "Course notes"
    assert payload["status"] == "queued"
    assert payload["config"] == {"filename": "course notes.pdf", "size_bytes": len(data)}

    served = await client.get(f"/api/v1/sources/{payload['id']}/file")
    assert served.status_code == 200
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["content-disposition"] == ("inline; filename*=UTF-8''course%20notes.pdf")
    assert served.content == data


async def test_pdf_title_falls_back_to_filename(client: AsyncClient, notebook_id: str) -> None:
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "pdf"},
        files={"file": ("lecture-3.pdf", make_pdf(["Text"]), "application/pdf")},
    )

    assert created.status_code == 201
    assert created.json()["title"] == "lecture-3"


async def test_source_without_a_file_returns_404(client: AsyncClient, notebook_id: str) -> None:
    source_id = uuid.uuid4()
    response = await client.get(f"/api/v1/sources/{source_id}/file")
    assert response.status_code == 404
    assert response.json() == {"detail": "Source file not found"}


@pytest.mark.parametrize(
    ("data", "files", "expected_status"),
    [
        ({"kind": "pdf"}, None, 422),
        ({"kind": "pdf"}, {"file": ("empty.pdf", b"", "application/pdf")}, 422),
        ({"kind": "pdf"}, {"file": ("notes.txt", b"hello", "text/plain")}, 422),
        (
            {"kind": "text", "text": "hello"},
            {"file": ("notes.pdf", make_pdf(["Text"]), "application/pdf")},
            422,
        ),
        (
            {"kind": "pdf", "title": "x" * 201},
            {"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
            422,
        ),
    ],
)
async def test_invalid_pdf_upload_rejected(
    client: AsyncClient,
    notebook_id: str,
    data: dict[str, str],
    files: dict[str, tuple[str, bytes, str]] | None,
    expected_status: int,
) -> None:
    response = await client.post(f"/api/v1/notebooks/{notebook_id}/sources", data=data, files=files)
    assert response.status_code == expected_status


async def test_oversized_pdf_rejected(
    client: AsyncClient, notebook_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    data = b"%PDF-" + b"x" * (1024 * 1024)

    response = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "pdf"},
        files={"file": ("big.pdf", data, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "PDF must be 1 MB or smaller"}

import socket
import threading
import uuid
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session_factory
from app.main import app
from app.models import Notebook, Source, SourceContent
from app.services.ingestion import graph, web
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.web import Article
from app.services.ingestion.worker import process_next
from app.services.vector_store import delete_source, search_chunks
from tests.helpers import FakeEmbeddings


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id() -> AsyncIterator[uuid.UUID]:
    async with async_session_factory() as session:
        notebook = Notebook(name="URL tests")
        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)
        notebook_id = notebook.id

    yield notebook_id

    async with async_session_factory() as session:
        source_ids = list(
            await session.scalars(select(Source.id).where(Source.notebook_id == notebook_id))
        )
    for source_id in source_ids:
        await delete_source(str(source_id))

    async with async_session_factory() as session:
        notebook = await session.get(Notebook, notebook_id)
        if notebook is not None:
            await session.delete(notebook)
            await session.commit()


def _public_dns(host: str, port: int, **_: object) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _private_dns(host: str, port: int, **_: object) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]


def test_validate_public_url_accepts_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web.socket, "getaddrinfo", _public_dns)
    web.validate_public_url("https://example.com/article")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "not a url",
        "https://user:secret@example.com/",
        "http://localhost:8000/",
        "http://localhost.localdomain/",
    ],
)
def test_validate_public_url_rejects_unsafe_shapes(url: str) -> None:
    with pytest.raises(IngestionError):
        web.validate_public_url(url)


def test_validate_public_url_rejects_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web.socket, "getaddrinfo", _private_dns)
    with pytest.raises(IngestionError, match="publicly reachable"):
        web.validate_public_url("https://internal.example.com/")


async def test_create_url_source(client: AsyncClient) -> None:
    created_notebook = await client.post("/api/v1/notebooks", json={"name": "URL source"})
    notebook_id = created_notebook.json()["id"]

    try:
        response = await client.post(
            f"/api/v1/notebooks/{notebook_id}/sources",
            data={"kind": "url", "url": "https://example.com/article"},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["kind"] == "url"
        assert payload["status"] == "queued"
        assert payload["title"] == "example.com"
        assert payload["config"] == {
            "url": "https://example.com/article",
            "custom_title": False,
        }
    finally:
        await client.delete(f"/api/v1/notebooks/{notebook_id}")


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "url"},
        {"kind": "url", "url": "not-a-url"},
        {"kind": "url", "url": "file:///etc/passwd"},
        {"kind": "url", "url": "https://example.com", "title": "x" * 201},
    ],
)
async def test_invalid_url_source_rejected(
    client: AsyncClient, notebook_id: uuid.UUID, data: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data=data,
    )
    assert response.status_code == 422


async def test_content_endpoint_returns_snapshot(
    client: AsyncClient, notebook_id: uuid.UUID
) -> None:
    created = await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "text", "text": "Stored viewer text"},
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    content = await client.get(f"/api/v1/sources/{source_id}/content")
    assert content.status_code == 200
    assert content.json() == {
        "text": "Stored viewer text",
        "pages": None,
        "segments": None,
    }

    await client.delete(f"/api/v1/sources/{source_id}")
    missing = await client.get(f"/api/v1/sources/{source_id}/content")
    assert missing.status_code == 404


async def _create_url_source(notebook_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        source = Source(
            notebook_id=notebook_id,
            kind="url",
            title="example.com",
            config={"url": "https://example.com/article", "custom_title": False},
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source.id


async def test_url_pipeline_captures_page_metadata(
    notebook_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id = await _create_url_source(notebook_id)

    def fake_fetch(url: str) -> Article:
        assert url == "https://example.com/article"
        return Article(
            url="https://example.com/article",
            title="A real article title",
            description="Why this article exists",
            text="A real article title\n\nThe article body explains retrieval.",
        )

    monkeypatch.setattr(graph, "fetch_article", fake_fetch)

    assert await process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        content = await session.get(SourceContent, source_id)
        assert source is not None
        assert content is not None
        assert source.status == "ready"
        assert source.title == "A real article title"
        assert source.char_count == len(content.text or "")
        assert content.text == "A real article title\n\nThe article body explains retrieval."
        assert source.config["final_url"] == "https://example.com/article"
        assert source.config["description"] == "Why this article exists"
        assert source.chunk_count == 1

    results = await search_chunks(
        str(notebook_id),
        "retrieval",
        embeddings=FakeEmbeddings(),
    )
    assert results
    assert results[0][0].metadata["source_id"] == str(source_id)
    assert "page" not in results[0][0].metadata


async def test_url_pipeline_marks_junk_url_failed(
    notebook_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id = await _create_url_source(notebook_id)

    def fake_fetch(url: str) -> Article:
        raise IngestionError("URL must be publicly reachable")

    monkeypatch.setattr(graph, "fetch_article", fake_fetch)

    assert await process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "failed"
        assert source.stage is None
        assert source.error == "URL must be publicly reachable"


def test_fetch_article_parses_html(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (
        b"<html><head><title>Local test article</title>"
        b"<meta name='description' content='A local description'></head>"
        b"<body><p>First paragraph.</p><p>Second paragraph.</p></body></html>"
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setattr(web, "validate_public_url", lambda url: None)
        article = web.fetch_article(f"http://127.0.0.1:{server.server_port}/")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert article.title == "Local test article"
    assert article.description == "A local description"
    assert "First paragraph." in article.text
    assert "Second paragraph." in article.text
    assert "\n" in article.text

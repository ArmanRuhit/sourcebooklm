import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session_factory
from app.main import app
from app.models import Notebook, Source, SourceContent
from app.services.ingestion import graph, web
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.web import VideoTranscript
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
        notebook = Notebook(name="YouTube tests")
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


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(url: str, expected: str) -> None:
    assert web.extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=too-short",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=abc",
    ],
)
def test_extract_video_id_rejects_non_videos(url: str) -> None:
    with pytest.raises(IngestionError):
        web.extract_video_id(url)


async def test_create_youtube_source(client: AsyncClient) -> None:
    created_notebook = await client.post("/api/v1/notebooks", json={"name": "YouTube source"})
    notebook_id = created_notebook.json()["id"]

    try:
        response = await client.post(
            f"/api/v1/notebooks/{notebook_id}/sources",
            data={
                "kind": "youtube",
                "url": "https://youtu.be/dQw4w9WgXcQ?si=tracking",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "youtube"
        assert body["status"] == "queued"
        assert body["title"] == "YouTube video"
        assert body["config"]["video_id"] == "dQw4w9WgXcQ"
        assert body["config"]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert body["config"]["custom_title"] is False
    finally:
        await client.delete(f"/api/v1/notebooks/{notebook_id}")


async def test_create_youtube_source_rejects_bad_url(client: AsyncClient) -> None:
    created_notebook = await client.post("/api/v1/notebooks", json={"name": "Bad YouTube"})
    notebook_id = created_notebook.json()["id"]

    try:
        response = await client.post(
            f"/api/v1/notebooks/{notebook_id}/sources",
            data={"kind": "youtube", "url": "https://example.com/video"},
        )

        assert response.status_code == 422
        assert "not a YouTube video" in response.json()["detail"]
    finally:
        await client.delete(f"/api/v1/notebooks/{notebook_id}")


async def _create_youtube_source(
    notebook_id: uuid.UUID, *, custom_title: str | None = None
) -> uuid.UUID:
    async with async_session_factory() as session:
        source = Source(
            notebook_id=notebook_id,
            kind="youtube",
            title=custom_title or "YouTube video",
            config={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "video_id": "dQw4w9WgXcQ",
                "custom_title": custom_title is not None,
            },
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source.id


async def test_youtube_pipeline_stores_timed_segments(
    notebook_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id = await _create_youtube_source(notebook_id)

    def fake_fetch(url: str) -> VideoTranscript:
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        return VideoTranscript(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="A useful talk",
            cues=(
                ("First idea about retrieval.", 0.0, 3.5),
                ("Second idea about citations.", 3.5, 8.0),
                ("Final idea about evaluation.", 8.0, 12.0),
            ),
        )

    monkeypatch.setattr(graph, "fetch_transcript", fake_fetch)

    assert await process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        content = await session.get(SourceContent, source_id)
        assert source is not None
        assert content is not None
        assert source.status == "ready"
        assert source.title == "A useful talk"
        assert source.char_count == len(content.text or "")
        assert content.segments is not None
        assert len(content.segments) == 3
        assert content.segments[0] == {
            "text": "First idea about retrieval.",
            "start_seconds": 0.0,
            "end_seconds": 3.5,
        }
        assert "Final idea about evaluation." in (content.text or "")
        assert source.chunk_count == 1
        assert source.config["video_id"] == "dQw4w9WgXcQ"

    results = await search_chunks(
        str(notebook_id),
        "citations",
        embeddings=FakeEmbeddings(),
    )
    assert results
    metadata = results[0][0].metadata
    assert metadata["source_id"] == str(source_id)
    assert metadata["start_seconds"] == 0.0
    assert metadata["end_seconds"] == 12.0
    assert "page" not in metadata


async def test_youtube_pipeline_marks_disabled_transcript_failed(
    notebook_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id = await _create_youtube_source(notebook_id)

    def fake_fetch(url: str) -> VideoTranscript:
        raise IngestionError("Transcripts are disabled for that video")

    monkeypatch.setattr(graph, "fetch_transcript", fake_fetch)

    assert await process_next(embeddings=FakeEmbeddings()) is True

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "failed"
        assert source.stage is None
        assert source.error == "Transcripts are disabled for that video"

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.main import app
from app.models import Notebook, Source, SourceContent
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.vtt import parse_vtt
from app.services.ingestion.worker import process_next
from app.services.vector_store import delete_source, search_chunks
from tests.helpers import FakeEmbeddings

VTT_SAMPLE = (
    b"\xef\xbb\xbfWEBVTT\r\n"
    b"Kind: captions\r\n"
    b"Language: en\r\n"
    b"\r\n"
    b"intro\r\n"
    b"00:00:01.000 --> 00:00:04.500 align:start position:0%\r\n"
    b"Hello <b>world</b>\r\n"
    b"\r\n"
    b"00:05.000 --> 00:00:07.250\r\n"
    b"Second &amp; last\r\n"
)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def notebook_id() -> AsyncIterator[uuid.UUID]:
    async with async_session_factory() as session:
        notebook = Notebook(name="VTT tests")
        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)
        created_id = notebook.id

    yield created_id

    async with async_session_factory() as session:
        source_ids = list(
            await session.scalars(select(Source.id).where(Source.notebook_id == created_id))
        )
    for source_id in source_ids:
        await delete_source(str(source_id))

    async with async_session_factory() as session:
        notebook = await session.get(Notebook, created_id)
        if notebook is not None:
            await session.delete(notebook)
            await session.commit()


def test_parse_vtt_cues_with_settings_and_markup() -> None:
    assert parse_vtt(VTT_SAMPLE) == [
        ("Hello world", 1.0, 4.5),
        ("Second & last", 5.0, 7.25),
    ]


@pytest.mark.parametrize(
    "data",
    [
        b"not a vtt file",
        b"WEBVTT\n\n00:00:xx.000 --> 00:00:02.000\nbroken\n",
        b"WEBVTT\n\n00:00:02.000 --> 00:00:01.000\nbackwards\n",
        b"WEBVTT\n\nNOTE this is only a comment\n",
    ],
)
def test_parse_vtt_rejects_malformed_files(data: bytes) -> None:
    with pytest.raises(IngestionError):
        parse_vtt(data)


async def _post_vtt(
    client: AsyncClient,
    notebook_id: uuid.UUID,
    *,
    data: bytes = VTT_SAMPLE,
    filename: str = "talk.vtt",
):
    return await client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        data={"kind": "vtt"},
        files={"file": (filename, data, "text/vtt")},
    )


async def test_create_vtt_source_and_stream_file(
    client: AsyncClient, notebook_id: uuid.UUID
) -> None:
    response = await _post_vtt(client, notebook_id)
    assert response.status_code == 201, response.text

    created = response.json()
    assert created["kind"] == "vtt"
    assert created["status"] == "queued"
    assert created["title"] == "talk"
    assert created["config"]["filename"] == "talk.vtt"
    assert created["config"]["size_bytes"] == len(VTT_SAMPLE)

    streamed = await client.get(f"/api/v1/sources/{created['id']}/file")
    assert streamed.status_code == 200
    assert streamed.content == VTT_SAMPLE
    assert streamed.headers["content-type"].startswith("text/vtt")


async def test_create_vtt_rejects_invalid_files(
    client: AsyncClient, notebook_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong_extension = await _post_vtt(client, notebook_id, data=VTT_SAMPLE, filename="talk.txt")
    assert wrong_extension.status_code == 422
    assert wrong_extension.json()["detail"] == "File must be a .vtt transcript"

    wrong_magic = await _post_vtt(client, notebook_id, data=b"hello", filename="talk.vtt")
    assert wrong_magic.status_code == 422
    assert wrong_magic.json()["detail"] == "File must be a WebVTT (.vtt) file"

    empty = await _post_vtt(client, notebook_id, data=b"", filename="talk.vtt")
    assert empty.status_code == 422
    assert empty.json()["detail"] == "The uploaded VTT is empty"

    missing = await client.post(f"/api/v1/notebooks/{notebook_id}/sources", data={"kind": "vtt"})
    assert missing.status_code == 422
    assert missing.json()["detail"] == "A VTT file is required"

    monkeypatch.setattr(settings, "max_upload_mb", 0)
    oversize = await _post_vtt(client, notebook_id, data=VTT_SAMPLE)
    assert oversize.status_code == 413
    assert "0 MB or smaller" in oversize.json()["detail"]


async def test_vtt_pipeline_preserves_cue_times(
    client: AsyncClient, notebook_id: uuid.UUID
) -> None:
    response = await _post_vtt(client, notebook_id)
    source_id = uuid.UUID(response.json()["id"])

    await process_next(FakeEmbeddings())

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "ready"
        assert source.chunk_count == 1
        assert source.char_count == len("Hello world\nSecond & last")

        content = await session.get(SourceContent, source_id)
        assert content is not None
        assert content.text == "Hello world\nSecond & last"
        assert content.segments == [
            {"text": "Hello world", "start_seconds": 1.0, "end_seconds": 4.5},
            {"text": "Second & last", "start_seconds": 5.0, "end_seconds": 7.25},
        ]

    results = await search_chunks(str(notebook_id), "Hello world", k=4, embeddings=FakeEmbeddings())
    assert results
    metadata = results[0][0].metadata
    assert metadata["start_seconds"] == 1.0
    assert metadata["end_seconds"] == 7.25
    assert "page" not in metadata


async def test_malformed_vtt_fails_ingestion(client: AsyncClient, notebook_id: uuid.UUID) -> None:
    response = await _post_vtt(
        client,
        notebook_id,
        data=b"WEBVTT\n\n00:00:bad --> 00:00:02.000\nbroken\n",
    )
    source_id = uuid.UUID(response.json()["id"])

    await process_next(FakeEmbeddings())

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        assert source is not None
        assert source.status == "failed"
        assert source.stage is None
        assert "Could not parse WebVTT timestamp" in (source.error or "")

"""LangGraph ingestion pipeline: extract -> chunk -> embed and index.

The graph is deliberately small and deterministic. Each node commits its stage
so the UI can poll progress; any exception bubbles to the worker boundary,
which marks the source `failed` and removes partial vectors.
"""

import uuid
from typing import Any, TypedDict, cast

from langchain_core.embeddings import Embeddings
from langgraph.graph import END, START, StateGraph
from sqlalchemy import CursorResult, func, update
from starlette.concurrency import run_in_threadpool

from app.db import async_session_factory
from app.models import Source, SourceContent, SourceFile
from app.services import vector_store
from app.services.ingestion.chunker import Chunk, split_pages, split_text, split_transcript
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.pdf import extract_pages
from app.services.ingestion.vtt import parse_vtt
from app.services.ingestion.web import fetch_article, fetch_transcript


class IngestState(TypedDict, total=False):
    """Data passed between graph nodes."""

    source_id: str
    notebook_id: str
    kind: str
    title: str
    text: str
    pages: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    chunks: list[Chunk]


async def _set_stage(source_id: uuid.UUID, stage: str) -> None:
    """Persist a stage transition so polling clients see progress."""
    async with async_session_factory() as session:
        await session.execute(
            update(Source).where(Source.id == source_id).values(stage=stage, updated_at=func.now())
        )
        await session.commit()


async def _extract(state: IngestState) -> dict[str, Any]:
    """Load text (or extract PDF pages) and advance to chunking."""
    source_id = uuid.UUID(state["source_id"])

    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            raise IngestionError("Source disappeared before extraction")

        if source.kind == "youtube":
            config = dict(source.config or {})
            video = await run_in_threadpool(fetch_transcript, str(config.get("url") or ""))

            segments: list[dict[str, Any]] = [
                {
                    "text": text,
                    "start_seconds": start,
                    "end_seconds": end,
                }
                for text, start, end in video.cues
            ]
            content = await session.get(SourceContent, source_id)
            if content is None:
                content = SourceContent(source_id=source_id)
                session.add(content)
            content.text = "\n".join(text for text, _, _ in video.cues)
            content.pages = None
            content.segments = segments

            source.char_count = len(content.text)
            source.stage = "chunking"
            if not config.get("custom_title") and video.title:
                source.title = video.title
            source.config = {
                **config,
                "final_url": video.url,
                "video_id": video.video_id,
            }
            await session.commit()

            return {
                "text": content.text,
                "segments": segments,
                "notebook_id": str(source.notebook_id),
                "kind": source.kind,
                "title": source.title,
            }

        if source.kind == "vtt":
            uploaded = await session.get(SourceFile, source_id)
            if uploaded is None:
                raise IngestionError("Uploaded VTT file is missing")

            cues = await run_in_threadpool(parse_vtt, uploaded.file_bytes)
            segments = [
                {
                    "text": text,
                    "start_seconds": start,
                    "end_seconds": end,
                }
                for text, start, end in cues
            ]
            content = await session.get(SourceContent, source_id)
            if content is None:
                content = SourceContent(source_id=source_id)
                session.add(content)
            content.text = "\n".join(text for text, _, _ in cues)
            content.pages = None
            content.segments = segments

            source.char_count = len(content.text)
            source.stage = "chunking"
            await session.commit()

            return {
                "text": content.text,
                "segments": segments,
                "notebook_id": str(source.notebook_id),
                "kind": source.kind,
                "title": source.title,
            }

        if source.kind == "url":
            config = dict(source.config or {})
            article = await run_in_threadpool(fetch_article, str(config.get("url") or ""))

            content = await session.get(SourceContent, source_id)
            if content is None:
                content = SourceContent(source_id=source_id)
                session.add(content)
            content.text = article.text
            content.pages = None

            source.char_count = len(article.text)
            source.stage = "chunking"
            if not config.get("custom_title") and article.title:
                source.title = article.title
            source.config = {
                **config,
                "final_url": article.url,
                **({"description": article.description} if article.description else {}),
            }
            await session.commit()

            return {
                "text": article.text,
                "notebook_id": str(source.notebook_id),
                "kind": source.kind,
                "title": source.title,
            }

        if source.kind == "pdf":
            uploaded = await session.get(SourceFile, source_id)
            if uploaded is None:
                raise IngestionError("Uploaded PDF is missing")

            pages = await run_in_threadpool(extract_pages, uploaded.file_bytes)
            text = "\n\n".join(page["text"] for page in pages)
            content = await session.get(SourceContent, source_id)
            if content is None:
                content = SourceContent(source_id=source_id)
                session.add(content)
            content.text = None
            content.pages = pages

            source.char_count = len(text)
            source.stage = "chunking"
            await session.commit()

            return {
                "text": text,
                "pages": pages,
                "notebook_id": str(source.notebook_id),
                "kind": source.kind,
                "title": source.title,
            }

        content = await session.get(SourceContent, source_id)
        if content is None or not content.text:
            raise IngestionError("No text content to ingest")

        text = content.text
        source.char_count = len(text)
        source.stage = "chunking"
        await session.commit()

        return {
            "text": text,
            "notebook_id": str(source.notebook_id),
            "kind": source.kind,
            "title": source.title,
        }


async def _chunk(state: IngestState) -> dict[str, Any]:
    """Split the snapshot into overlapping, offset-aware chunks."""
    try:
        if state.get("segments"):
            chunks = await run_in_threadpool(
                split_transcript,
                [
                    (
                        str(segment["text"]),
                        float(segment["start_seconds"]),
                        float(segment["end_seconds"]),
                    )
                    for segment in state["segments"]
                ],
            )
        elif state.get("pages"):
            chunks = await run_in_threadpool(
                split_pages,
                ((int(page["page"]), str(page["text"])) for page in state["pages"]),
            )
        else:
            chunks = split_text(state["text"])
    except ValueError as exc:
        raise IngestionError(str(exc)) from exc

    await _set_stage(uuid.UUID(state["source_id"]), "embedding")
    return {"chunks": chunks}


async def _embed_and_index(
    state: IngestState,
    embeddings: Embeddings | None,
) -> dict[str, Any]:
    """Embed, upsert into PGVector, and mark the source ready."""
    source_id = state["source_id"]
    count = await vector_store.index_chunks(
        notebook_id=state["notebook_id"],
        source_id=source_id,
        source_type=state["kind"],
        title=state["title"],
        chunks=state["chunks"],
        embeddings=embeddings,
    )
    await _set_stage(uuid.UUID(source_id), "indexing")

    async with async_session_factory() as session:
        result = await session.execute(
            update(Source)
            .where(Source.id == uuid.UUID(source_id))
            .values(
                status="ready",
                stage=None,
                error=None,
                chunk_count=count,
                updated_at=func.now(),
            )
        )
        if cast("CursorResult[Any]", result).rowcount == 0:
            raise IngestionError("Source was removed during ingestion")
        await session.commit()

    return {}


def build_graph(embeddings: Embeddings | None = None) -> Any:
    """Compile the ingestion graph for one worker (optionally test embeddings)."""

    async def index_node(state: IngestState) -> dict[str, Any]:
        return await _embed_and_index(state, embeddings)

    builder = StateGraph(IngestState)
    builder.add_node("extract", _extract)
    builder.add_node("chunk", _chunk)
    builder.add_node("embed_and_index", index_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "chunk")
    builder.add_edge("chunk", "embed_and_index")
    builder.add_edge("embed_and_index", END)
    return builder.compile()


async def run_ingestion(
    source_id: uuid.UUID,
    *,
    embeddings: Embeddings | None = None,
) -> None:
    """Run the graph to completion; raises on the first node failure."""
    await build_graph(embeddings).ainvoke({"source_id": str(source_id)})

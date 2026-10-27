"""Retrieval quality harness: seed a fixture notebook and measure hit@k/MRR.

Run with real embeddings (default) or deterministic fake embeddings:

    uv run python -m app.evals.retrieval
    uv run python -m app.evals.retrieval --fake --lambdas 0.3,0.5,0.7
    uv run python -m app.evals.retrieval --expand

The fixture notebook is deleted afterwards unless --keep is passed.
"""

import argparse
import asyncio
import math
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.embeddings import Embeddings
from sqlalchemy import select

from app.db import async_session_factory
from app.models import Notebook, Source, SourceContent
from app.services import vector_store
from app.services.ingestion.chunker import split_pages, split_text, split_transcript
from app.services.rag import retriever


@dataclass(frozen=True)
class Fixture:
    key: str
    kind: str
    title: str
    text: str
    pages: list[dict[str, Any]] | None = None
    segments: list[dict[str, Any]] | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected: str


FIXTURES = [
    Fixture(
        key="rag",
        kind="text",
        title="RAG fundamentals",
        text=(
            "Chunk overlap keeps words from both sides of a split boundary in the same "
            "embedding, so a sentence divided between two chunks is still retrievable. "
            "Maximal marginal relevance (MMR) selects results that are relevant to the "
            "query but dissimilar from each other, balancing relevance and diversity. "
            "A cross-encoder reranker scores query-passage pairs after the first-stage "
            "search and improves precision."
        ),
    ),
    Fixture(
        key="raft",
        kind="pdf",
        title="Raft consensus notes",
        text="",
        pages=[
            {
                "page": 1,
                "text": (
                    "Raft is a consensus algorithm. A follower becomes a candidate after "
                    "a randomized election timeout, requests votes, and a majority elects "
                    "the leader for the next term."
                ),
            },
            {
                "page": 2,
                "text": (
                    "The leader appends entries to its log and replicates them to "
                    "followers. An entry is committed once a majority stores it and the "
                    "leader advances the commit index."
                ),
            },
            {
                "page": 3,
                "text": (
                    "During a network partition only the side with a majority can elect "
                    "a leader and commit entries. The minority cannot make progress, "
                    "which prevents split-brain."
                ),
            },
        ],
    ),
    Fixture(
        key="postgres",
        kind="url",
        title="Postgres vector indexes",
        text=(
            "HNSW builds a hierarchical graph of vectors and walks it during search. It "
            "offers high recall and fast queries but needs more memory. IVFFlat clusters "
            "vectors into lists and probes only a subset, so it builds faster and uses "
            "less memory but can miss neighbors. pgvector supports L2, inner product, "
            "and cosine distance; the index operator class must match the query distance."
        ),
        config={"url": "https://example.com/vector-indexes"},
    ),
    Fixture(
        key="langgraph",
        kind="youtube",
        title="LangGraph walkthrough",
        text="",
        config={"url": "https://www.youtube.com/watch?v=eval", "video_id": "eval0000000"},
        segments=[
            {
                "text": "A state graph is made of nodes that read and update a shared state.",
                "start_seconds": 0.0,
                "end_seconds": 6.0,
            },
            {
                "text": "Edges connect nodes. Conditional edges choose the next node at runtime.",
                "start_seconds": 6.0,
                "end_seconds": 12.0,
            },
            {
                "text": (
                    "Checkpoints persist state after each step so a run can resume or be "
                    "inspected later."
                ),
                "start_seconds": 12.0,
                "end_seconds": 19.0,
            },
            {
                "text": "A reducer decides how updates from parallel branches merge into state.",
                "start_seconds": 19.0,
                "end_seconds": 26.0,
            },
        ],
    ),
    Fixture(
        key="incident",
        kind="vtt",
        title="Incident review",
        text="",
        segments=[
            {
                "text": (
                    "Retries should use exponential backoff with jitter so clients do not "
                    "synchronize their retry storms."
                ),
                "start_seconds": 0.0,
                "end_seconds": 8.0,
            },
            {
                "text": (
                    "A circuit breaker stops sending requests after repeated failures and "
                    "probes for recovery after a cool-down."
                ),
                "start_seconds": 8.0,
                "end_seconds": 16.0,
            },
            {
                "text": (
                    "Idempotency keys let a client retry a write without creating a "
                    "duplicate record."
                ),
                "start_seconds": 16.0,
                "end_seconds": 23.0,
            },
        ],
    ),
    Fixture(
        key="cooking",
        kind="text",
        title="Bread baking",
        text=(
            "Sourdough gets oven spring from steam in a covered Dutch oven, a strong "
            "starter, and a shaped dough with enough tension. Bake at high heat, then "
            "uncover to brown the crust."
        ),
    ),
]

EVAL_CASES = [
    EvalCase("Why do sentences survive when a document is split into pieces?", "rag"),
    EvalCase("What does MMR balance when selecting chunks?", "rag"),
    EvalCase("How does Raft choose a leader?", "raft"),
    EvalCase("When is a Raft log entry considered committed?", "raft"),
    EvalCase("What keeps a cluster from split-brain when the network fails?", "raft"),
    EvalCase("Which index builds a graph to trade memory for recall?", "postgres"),
    EvalCase("What is the difference between HNSW and IVFFlat?", "postgres"),
    EvalCase("Which distance does pgvector support?", "postgres"),
    EvalCase("How do nodes and edges work in LangGraph?", "langgraph"),
    EvalCase("How can a workflow resume after a crash?", "langgraph"),
    EvalCase("When does a conditional edge run?", "langgraph"),
    EvalCase("How should retries use backoff?", "incident"),
    EvalCase("What stops a client from hammering a failing service?", "incident"),
    EvalCase("Why are idempotency keys useful during retries?", "incident"),
    EvalCase("How do I get better oven spring?", "cooking"),
]


class _FakeEmbeddings(Embeddings):
    """Deterministic 1536-d hashed bag-of-words, for offline comparisons."""

    dimensions = 1536

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            vector[hash(token) % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _chunks(fixture: Fixture, transcript_chunk_size: int):
    if fixture.segments:
        cues = [
            (segment["text"], segment["start_seconds"], segment["end_seconds"])
            for segment in fixture.segments
        ]
        return split_transcript(cues, chunk_size=transcript_chunk_size)
    if fixture.pages:
        return split_pages((page["page"], page["text"]) for page in fixture.pages)
    return split_text(fixture.text)


async def _seed(
    notebook_id: uuid.UUID,
    fixture: Fixture,
    embeddings: Embeddings,
    transcript_chunk_size: int,
) -> uuid.UUID:
    async with async_session_factory() as session:
        text = fixture.text or "\n\n".join(
            item["text"] for item in (fixture.pages or fixture.segments or [])
        )
        source = Source(
            notebook_id=notebook_id,
            kind=fixture.kind,
            title=fixture.title,
            status="ready",
            config=fixture.config,
        )
        session.add(source)
        await session.flush()
        session.add(
            SourceContent(
                source_id=source.id,
                text=text,
                pages=fixture.pages,
                segments=fixture.segments,
            )
        )
        chunks = _chunks(fixture, transcript_chunk_size)
        count = await vector_store.index_chunks(
            notebook_id=str(notebook_id),
            source_id=str(source.id),
            source_type=fixture.kind,
            title=fixture.title,
            chunks=chunks,
            embeddings=embeddings,
        )
        source.chunk_count = count
        source.char_count = len(text)
        source_id = source.id
        await session.commit()
        return source_id


async def _build_fixture(
    embeddings: Embeddings, transcript_chunk_size: int
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    async with async_session_factory() as session:
        notebook = Notebook(name=f"Retrieval eval {uuid.uuid4().hex[:8]}")
        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)
        notebook_id = notebook.id

    source_ids: dict[str, uuid.UUID] = {}
    for fixture in FIXTURES:
        source_ids[fixture.key] = await _seed(
            notebook_id, fixture, embeddings, transcript_chunk_size
        )
    return notebook_id, source_ids


async def _cleanup(notebook_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        notebook = await session.get(Notebook, notebook_id)
        if notebook is None:
            return
        sources = (
            await session.scalars(select(Source).where(Source.notebook_id == notebook_id))
        ).all()
        for source in sources:
            await vector_store.delete_source(str(source.id))
        await session.delete(notebook)
        await session.commit()


def _metrics(
    results: list[list[Any]], source_ids: dict[str, uuid.UUID]
) -> tuple[float, float, float, float]:
    hits = {1: 0, 3: 0, 6: 0}
    reciprocal = 0.0

    for case, documents in zip(EVAL_CASES, results, strict=True):
        expected = str(source_ids[case.expected])
        rank = next(
            (
                index
                for index, document in enumerate(documents, start=1)
                if str(document.metadata.get("source_id")) == expected
            ),
            None,
        )
        if rank is not None:
            reciprocal += 1.0 / rank
            for cutoff in hits:
                if rank <= cutoff:
                    hits[cutoff] += 1

    total = len(EVAL_CASES)
    return hits[1] / total, hits[3] / total, hits[6] / total, reciprocal / total


async def _evaluate(
    notebook_id: uuid.UUID,
    source_ids: dict[str, uuid.UUID],
    embeddings: Embeddings,
    *,
    lambda_mult: float,
    expand: bool,
    use_rerank: bool,
) -> tuple[float, float, float, float, list[list[Any]]]:
    results = []
    for case in EVAL_CASES:
        documents = await retriever.retrieve(
            str(notebook_id),
            case.question,
            embeddings=embeddings,
            lambda_mult=lambda_mult,
            expand=expand,
            use_rerank=use_rerank,
        )
        results.append(documents)
    return (*_metrics(results, source_ids), results)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", help="use deterministic fake embeddings")
    parser.add_argument("--lambdas", default="0.5", help="comma-separated MMR lambda values")
    parser.add_argument("--expand", action="store_true", help="enable LLM multi-query fusion")
    parser.add_argument("--rerank", action="store_true", help="enable LLM passage reranking")
    parser.add_argument("--transcript-chunk-size", type=int, default=1000)
    parser.add_argument("--keep", action="store_true", help="keep the fixture notebook")
    args = parser.parse_args()

    if args.fake:
        embeddings: Embeddings = _FakeEmbeddings()
        label = "fake"
    else:
        embeddings = vector_store.get_embeddings()
        label = "real"

    notebook_id, source_ids = await _build_fixture(embeddings, args.transcript_chunk_size)
    print(
        f"fixture notebook {notebook_id} · embeddings={label} · "
        f"cases={len(EVAL_CASES)} · transcript_chunk={args.transcript_chunk_size}"
    )

    try:
        for raw in args.lambdas.split(","):
            lambda_mult = float(raw)
            hit1, hit3, hit6, mrr, results = await _evaluate(
                notebook_id,
                source_ids,
                embeddings,
                lambda_mult=lambda_mult,
                expand=args.expand,
                use_rerank=args.rerank,
            )
            mode = "expand" if args.expand else "rerank" if args.rerank else "baseline"
            print(
                f"{mode:8} lambda={lambda_mult:.2f}  "
                f"hit@1={hit1:.2f}  hit@3={hit3:.2f}  hit@6={hit6:.2f}  MRR={mrr:.3f}"
            )
            for case, documents in zip(EVAL_CASES, results, strict=True):
                expected = str(source_ids[case.expected])
                rank = next(
                    (
                        index
                        for index, document in enumerate(documents, start=1)
                        if str(document.metadata.get("source_id")) == expected
                    ),
                    None,
                )
                print(f"  {rank or '-':>2}  {case.expected:9} {case.question}")
    finally:
        if args.keep:
            print(f"kept fixture notebook {notebook_id}")
        else:
            await _cleanup(notebook_id)
            print("fixture notebook removed")


if __name__ == "__main__":
    asyncio.run(main())

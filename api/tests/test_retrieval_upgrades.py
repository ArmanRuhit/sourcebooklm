"""Retrieval upgrades: reranking, query expansion, and eval fixture integrity."""

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from app.evals.retrieval import EVAL_CASES, FIXTURES
from app.services.rag.expansion import expand_question
from app.services.rag.rerank import rerank_documents


class FakeModel:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def ainvoke(self, _messages: object) -> AIMessage:
        return AIMessage(content=self.reply)


class FailingModel:
    async def ainvoke(self, _messages: object) -> AIMessage:
        raise RuntimeError("provider down")


def _documents() -> list[Document]:
    return [
        Document(page_content="alpha", metadata={"source_id": "a", "chunk_index": 0}),
        Document(page_content="beta", metadata={"source_id": "b", "chunk_index": 0}),
        Document(page_content="gamma", metadata={"source_id": "c", "chunk_index": 0}),
    ]


async def test_rerank_reorders_by_model_output() -> None:
    documents = await rerank_documents("question", _documents(), model=FakeModel("3,1,2"))

    assert [document.metadata["source_id"] for document in documents] == ["c", "a", "b"]


async def test_rerank_keeps_order_when_model_fails() -> None:
    documents = await rerank_documents("question", _documents(), model=FailingModel())

    assert [document.metadata["source_id"] for document in documents] == ["a", "b", "c"]


async def test_expand_question_deduplicates_variants() -> None:
    queries = await expand_question(
        "How does MMR work?",
        model=FakeModel("How does maximal marginal relevance work?\nHow does MMR work?"),
    )

    assert queries == ["How does MMR work?", "How does maximal marginal relevance work?"]


async def test_expand_question_falls_back_without_provider() -> None:
    queries = await expand_question("How does MMR work?", model=FailingModel())

    assert queries == ["How does MMR work?"]


def test_eval_fixture_covers_every_expected_source() -> None:
    keys = {fixture.key for fixture in FIXTURES}
    expected = {case.expected for case in EVAL_CASES}

    assert 12 <= len(EVAL_CASES) <= 15
    assert expected <= keys
    assert len(keys) >= 5

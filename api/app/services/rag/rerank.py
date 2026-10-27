"""Best-effort LLM reranking for retrieved passages."""

import logging
import re

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import llm

logger = logging.getLogger(__name__)

MAX_PASSAGE_CHARS = 500
RERANK_PROMPT = """Rank the numbered passages by how directly they answer the
question. Put the most useful passage first. Return only a comma-separated list
of passage numbers, for example: 3,1,2. Do not explain."""


def _message_text(message: object) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return str(content)


async def rerank_documents(
    question: str, documents: list[Document], *, model: object | None = None
) -> list[Document]:
    """Reorder passages by LLM-judged usefulness; preserve all documents."""
    if len(documents) < 2:
        return documents

    passages = "\n\n".join(
        f"[{index}] {document.page_content[:MAX_PASSAGE_CHARS]}"
        for index, document in enumerate(documents, start=1)
    )
    try:
        chat = model if model is not None else llm.get_chat_model()
        response = await chat.ainvoke(  # type: ignore[attr-defined]
            [
                SystemMessage(content=RERANK_PROMPT),
                HumanMessage(content=f"Question: {question}\n\nPassages:\n{passages}"),
            ]
        )
    except Exception:
        logger.warning("Reranking failed; keeping retrieval order", exc_info=True)
        return documents

    order: list[int] = []
    for raw in re.findall(r"\d+", _message_text(response)):
        index = int(raw) - 1
        if 0 <= index < len(documents) and index not in order:
            order.append(index)

    order.extend(index for index in range(len(documents)) if index not in order)
    return [documents[index] for index in order]

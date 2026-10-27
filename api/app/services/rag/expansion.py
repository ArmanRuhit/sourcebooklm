"""LLM-assisted multi-query expansion for retrieval."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import llm

logger = logging.getLogger(__name__)

MAX_QUERIES = 4

EXPANSION_PROMPT = """Rewrite the user's question as up to three short, diverse search
queries that would find the answer in a document collection. Use different
wording and include likely synonyms, but never invent facts or answers.
Return one query per line with no numbering or commentary."""


def _message_text(message: object) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


async def expand_question(question: str, *, model: object | None = None) -> list[str]:
    """Return the original question plus up to three paraphrased search queries.

    Expansion is best-effort: a missing key or provider error falls back to the
    original query so chat keeps working.
    """
    cleaned = question.strip()
    if not cleaned:
        return []

    try:
        chat = model if model is not None else llm.get_chat_model()
        response = await chat.ainvoke(  # type: ignore[attr-defined]
            [
                SystemMessage(content=EXPANSION_PROMPT),
                HumanMessage(content=cleaned),
            ]
        )
    except Exception:
        logger.warning("Query expansion failed; using the original question", exc_info=True)
        return [cleaned]

    queries = [cleaned]
    for line in _message_text(response).splitlines():
        candidate = line.strip().lstrip("-*0123456789. ").strip()
        if candidate and candidate.lower() not in {query.lower() for query in queries}:
            queries.append(candidate)
        if len(queries) >= MAX_QUERIES:
            break

    return queries

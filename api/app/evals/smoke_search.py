"""Similarity-search smoke check (P2.2).

Usage:
    uv run python -m app.evals.smoke_search --notebook <uuid> --query "your question"

Requires a configured OPENAI_API_KEY because the query is embedded with the same
model used at ingestion time.
"""

import argparse
import asyncio

from app.services.vector_store import search_chunks


async def _run(notebook_id: str, query: str, k: int) -> None:
    results = await search_chunks(notebook_id, query, k=k)
    if not results:
        print("No chunks found for this notebook.")
        return

    for rank, (document, score) in enumerate(results, start=1):
        metadata = document.metadata
        print(
            f"{rank}. score={score:.4f} title={metadata.get('title')!r} "
            f"chunk={metadata.get('chunk_index')} source={metadata.get('source_id')}"
        )
        print(f"   {document.page_content[:240]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search one notebook's indexed chunks")
    parser.add_argument("--notebook", required=True, help="Notebook UUID")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--k", type=int, default=5, help="Number of chunks to return")
    args = parser.parse_args()

    asyncio.run(_run(args.notebook, args.query, args.k))


if __name__ == "__main__":
    main()

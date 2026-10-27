"""Text chunking (technical design §5.4).

Plain text uses the recursive splitter at 1000 characters with 150 characters
of overlap. `add_start_index` makes every chunk cite an exact range in the
extracted snapshot.
"""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


@dataclass(frozen=True, slots=True)
class Chunk:
    """One embeddable slice of a source, with a traceable character range."""

    text: str
    index: int
    char_start: int
    char_end: int


def split_text(text: str) -> list[Chunk]:
    """Split text into overlapping chunks; empty input is an ingestion error."""
    if not text.strip():
        raise ValueError("Cannot chunk empty text")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )
    documents = splitter.create_documents([text])

    return [
        Chunk(
            text=document.page_content,
            index=index,
            char_start=int(document.metadata["start_index"]),
            char_end=int(document.metadata["start_index"]) + len(document.page_content),
        )
        for index, document in enumerate(documents)
    ]

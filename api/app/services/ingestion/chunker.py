"""Text chunking (technical design §5.4).

Plain text uses the recursive splitter at 1000 characters with 150 characters
of overlap. PDFs are split per page so every chunk keeps a citable page number.
`add_start_index` makes each chunk cite an exact range in its page or text.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


@dataclass(frozen=True, slots=True)
class Chunk:
    """One embeddable slice of a source, with a traceable range."""

    text: str
    index: int
    char_start: int
    char_end: int
    page: int | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )


def split_text(text: str) -> list[Chunk]:
    """Split text into overlapping chunks; empty input is an ingestion error."""
    if not text.strip():
        raise ValueError("Cannot chunk empty text")

    documents = _splitter().create_documents([text])

    return [
        Chunk(
            text=document.page_content,
            index=index,
            char_start=int(document.metadata["start_index"]),
            char_end=int(document.metadata["start_index"]) + len(document.page_content),
        )
        for index, document in enumerate(documents)
    ]


def split_pages(pages: Iterable[tuple[int, str]]) -> list[Chunk]:
    """Split each PDF page separately, preserving its 1-based page number."""
    chunks: list[Chunk] = []

    for page_number, text in pages:
        if not text.strip():
            continue
        for document in _splitter().create_documents([text]):
            start = int(document.metadata["start_index"])
            chunks.append(
                Chunk(
                    text=document.page_content,
                    index=len(chunks),
                    char_start=start,
                    char_end=start + len(document.page_content),
                    page=page_number,
                )
            )

    if not chunks:
        raise ValueError("Cannot chunk PDF with no extractable text")
    return chunks


def split_transcript(
    cues: Iterable[tuple[str, float, float]],
    *,
    chunk_size: int = CHUNK_SIZE,
) -> list[Chunk]:
    """Group timed cues into ~`chunk_size`-char chunks without splitting a cue.

    Each cue is ``(text, start_seconds, end_seconds)``. Chunks keep one cue of
    overlap, the first cue's start, and the last cue's end, so a citation can
    seek to the exact spoken range.
    """
    prepared: list[tuple[str, float, float, int]] = []
    offset = 0

    for text, start, end in cues:
        cleaned = text.strip()
        if not cleaned:
            continue
        prepared.append((cleaned, start, end, offset))
        offset += len(cleaned) + 1

    if not prepared:
        raise ValueError("Cannot chunk transcript with no cues")

    chunks: list[Chunk] = []
    current: list[tuple[str, float, float, int]] = []
    size = 0

    def flush() -> None:
        if not current:
            return
        text = " ".join(cue[0] for cue in current)
        chunks.append(
            Chunk(
                text=text,
                index=len(chunks),
                char_start=current[0][3],
                char_end=current[-1][3] + len(current[-1][0]),
                start_seconds=round(current[0][1], 2),
                end_seconds=round(current[-1][2], 2),
            )
        )

    for cue in prepared:
        addition = len(cue[0]) + (1 if current else 0)
        if current and size + addition > chunk_size:
            flush()
            current = [current[-1], cue]
            size = len(current[0][0]) + 1 + len(cue[0])
        else:
            current.append(cue)
            size += addition

    flush()
    return chunks

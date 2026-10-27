"""Chunker tests: sizes, overlap, and traceable offsets (P2.2)."""

import pytest

from app.services.ingestion.chunker import CHUNK_OVERLAP, CHUNK_SIZE, split_text


def test_short_text_is_one_chunk() -> None:
    chunks = split_text("Hello world")

    assert len(chunks) == 1
    assert chunks[0].text == "Hello world"
    assert chunks[0].index == 0
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len("Hello world")


def test_long_text_has_bounded_overlapping_chunks() -> None:
    text = "alpha beta gamma delta. " * 240

    chunks = split_text(text)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= CHUNK_SIZE for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end <= len(text)

    for previous, current in zip(chunks, chunks[1:], strict=False):
        overlap = previous.char_end - current.char_start
        assert 0 < overlap <= CHUNK_OVERLAP


@pytest.mark.parametrize("text", ["", "   \n\t  "])
def test_empty_text_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        split_text(text)

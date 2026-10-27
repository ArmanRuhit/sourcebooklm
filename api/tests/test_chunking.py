"""Chunker tests: sizes, overlap, and traceable offsets (P2.2)."""

import re

import pytest

from app.services.ingestion.chunker import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    split_text,
    split_transcript,
)


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


def test_short_transcript_is_one_timed_chunk() -> None:
    cues = [("Hello there.", 0.0, 2.0), ("General Kenobi.", 2.0, 5.25)]

    chunks = split_transcript(cues)

    assert len(chunks) == 1
    assert chunks[0].text == "Hello there. General Kenobi."
    assert chunks[0].start_seconds == 0.0
    assert chunks[0].end_seconds == 5.25
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len("Hello there. General Kenobi.")
    assert chunks[0].page is None


def test_long_transcript_keeps_one_cue_overlap() -> None:
    cues = [
        (f"Cue {index} " + "word " * 30, index * 10.0, index * 10.0 + 9.0) for index in range(20)
    ]

    chunks = split_transcript(cues)

    assert len(chunks) > 1
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.start_seconds is not None for chunk in chunks)
    assert chunks[0].start_seconds == 0.0
    assert chunks[-1].end_seconds == 199.0

    for previous, current in zip(chunks, chunks[1:], strict=False):
        previous_indices = [
            int(match.group(1)) for match in re.finditer(r"Cue (\d+)", previous.text)
        ]
        current_indices = [int(match.group(1)) for match in re.finditer(r"Cue (\d+)", current.text)]
        assert previous_indices[-1] == current_indices[0]
        assert current.start_seconds is not None
        assert previous.end_seconds is not None


@pytest.mark.parametrize("cues", [[], [("   ", 0.0, 1.0)]])
def test_empty_transcript_is_rejected(cues: list[tuple[str, float, float]]) -> None:
    with pytest.raises(ValueError, match="no cues"):
        split_transcript(cues)

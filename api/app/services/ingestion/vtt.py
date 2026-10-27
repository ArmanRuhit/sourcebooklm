"""Minimal WebVTT parser for transcript sources.

The app only needs cue text plus start/end seconds, so this intentionally
implements the small, stable subset of the format rather than pulling in a
full parser: an optional header, cue identifiers, timestamp settings, and
inline markup. Anything else is rejected with a readable ingestion error.
"""

import html
import re

from app.services.ingestion.errors import IngestionError

_HEADER = "WEBVTT"
_TIMESTAMP = re.compile(
    r"^(?:(?P<hours>\d{1,3}):)?(?P<minutes>\d{2}):(?P<seconds>\d{2})\.(?P<millis>\d{3})$"
)
_TAGS = re.compile(r"<[^>]*>")


def _parse_timestamp(value: str) -> float:
    match = _TIMESTAMP.match(value.strip())
    if match is None:
        raise IngestionError(f"Could not parse WebVTT timestamp: {value.strip()}")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int(match.group("millis"))

    if minutes >= 60 or seconds >= 60:
        raise IngestionError(f"Could not parse WebVTT timestamp: {value.strip()}")

    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_vtt(data: bytes) -> list[tuple[str, float, float]]:
    """Return `(text, start_seconds, end_seconds)` cues from a WebVTT file."""
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionError("VTT files must be UTF-8 encoded") from exc

    text = decoded.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    if not lines or not lines[0].startswith(_HEADER):
        raise IngestionError("File is not valid WebVTT (missing WEBVTT header)")

    cues: list[tuple[str, float, float]] = []
    block: list[str] = []

    def flush() -> None:
        if not block:
            return

        first = block[0].strip()
        if first.startswith(("NOTE", "STYLE", "REGION")):
            block.clear()
            return

        timestamp_index = next(
            (index for index, line in enumerate(block) if "-->" in line),
            None,
        )
        if timestamp_index is None:
            # Header metadata (Kind, Language, ...) can precede the first cue.
            if not cues:
                block.clear()
                return
            raise IngestionError("Could not parse WebVTT cue timestamps")

        timing = block[timestamp_index]
        start_raw, _, end_raw = timing.partition("-->")
        end_token = end_raw.strip().split(maxsplit=1)[0] if end_raw.strip() else ""
        start = _parse_timestamp(start_raw)
        end = _parse_timestamp(end_token)

        if end < start:
            raise IngestionError("WebVTT cue ends before it starts")

        cue_text = html.unescape(
            " ".join(_TAGS.sub("", line).strip() for line in block[timestamp_index + 1 :])
        ).strip()
        if cue_text:
            cues.append((cue_text, start, end))

        block.clear()

    for line in lines[1:]:
        if line.strip():
            block.append(line)
        else:
            flush()
    flush()

    if not cues:
        raise IngestionError("No transcript text found in that VTT file")

    return cues

"""Fetch and extract readable text from a public web page.

WebBaseLoader handles the HTML-to-text pass; this module adds the safety checks
the loader deliberately leaves to the caller (public-host validation, timeout,
and a stable error surface for the worker).
"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import requests
from langchain_community.document_loaders import WebBaseLoader
from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)

from app.services.ingestion.errors import IngestionError

FETCH_TIMEOUT_SECONDS = 15
USER_AGENT = "SourcebookLM/0.1 (+https://sourcebooklm.app)"
MAX_DESCRIPTION_LENGTH = 500
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
    "youtu.be",
    "www.youtu.be",
}
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True, slots=True)
class Article:
    """The subset of a web page we keep for a source."""

    url: str
    title: str | None
    description: str | None
    text: str


def validate_public_url(url: str) -> None:
    """Reject non-HTTP URLs and hosts that resolve to private addresses.

    This blocks the obvious SSRF cases (localhost, RFC1918, link-local metadata
    endpoints). Redirects are still followed by requests, so this is a first
    line of defence rather than a complete network sandbox.
    """
    parsed = urlsplit(url.strip())

    if parsed.scheme not in {"http", "https"}:
        raise IngestionError("URL must start with http:// or https://")
    if not parsed.hostname:
        raise IngestionError("URL is missing a host")
    if parsed.username or parsed.password:
        raise IngestionError("URL must not include credentials")

    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise IngestionError("URL must be publicly reachable")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except (socket.gaierror, UnicodeError) as exc:
        raise IngestionError("Could not resolve that URL's host") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise IngestionError("URL must be publicly reachable")


def _fetch_error(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "Timed out fetching that URL"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"That URL returned HTTP {exc.response.status_code}"
    return "Could not fetch that URL (the site may be offline or blocking requests)"


def fetch_article(url: str) -> Article:
    """Download a public article and return its text plus page metadata."""
    validate_public_url(url)

    loader = WebBaseLoader(
        url,
        raise_for_status=True,
        bs_get_text_kwargs={"separator": "\n"},
        requests_kwargs={
            "timeout": FETCH_TIMEOUT_SECONDS,
            "headers": {"User-Agent": USER_AGENT},
        },
    )

    try:
        documents = loader.load()
    except requests.RequestException as exc:
        raise IngestionError(_fetch_error(exc)) from exc

    if not documents:
        raise IngestionError("No readable text found at that URL")

    document = documents[0]
    text = document.page_content.strip()
    if not text:
        raise IngestionError("No readable text found at that URL")

    metadata = document.metadata
    title = metadata.get("title")
    description = metadata.get("description")

    return Article(
        url=str(metadata.get("source") or url),
        title=str(title).strip()[:200] if title else None,
        description=str(description).strip()[:MAX_DESCRIPTION_LENGTH] if description else None,
        text=text,
    )


@dataclass(frozen=True, slots=True)
class VideoTranscript:
    """A YouTube transcript with the video metadata we keep."""

    video_id: str
    url: str
    title: str | None
    cues: tuple[tuple[str, float, float], ...]


def extract_video_id(url: str) -> str:
    """Extract the 11-character video id from the common YouTube URL forms."""
    parsed = urlsplit(url.strip())

    if parsed.scheme not in {"http", "https"}:
        raise IngestionError("YouTube URL must start with http:// or https://")

    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise IngestionError("That URL is not a YouTube video")

    candidate: str | None = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [None])[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
            candidate = parts[1]

    if not candidate or not YOUTUBE_ID.fullmatch(candidate):
        raise IngestionError("Could not find a YouTube video ID in that URL")

    return candidate


def _fetch_title(video_id: str) -> str | None:
    """Best-effort oEmbed lookup; a missing title must not fail ingestion."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": watch_url, "format": "json"},
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        title = response.json().get("title")
    except (requests.RequestException, ValueError):
        return None

    return str(title).strip()[:200] if title else None


def fetch_transcript(url: str) -> VideoTranscript:
    """Fetch the English transcript and title for a YouTube video."""
    video_id = extract_video_id(url)

    try:
        fetched = YouTubeTranscriptApi().fetch(
            video_id,
            languages=("en", "en-US", "en-GB"),
            preserve_formatting=False,
        )
    except TranscriptsDisabled as exc:
        raise IngestionError("Transcripts are disabled for that video") from exc
    except NoTranscriptFound as exc:
        raise IngestionError("No English transcript is available for that video") from exc
    except VideoUnavailable as exc:
        raise IngestionError("That video is unavailable") from exc
    except VideoUnplayable as exc:
        raise IngestionError("That video cannot be played") from exc
    except AgeRestricted as exc:
        raise IngestionError("That video is age-restricted") from exc
    except (RequestBlocked, IpBlocked) as exc:
        raise IngestionError("YouTube blocked the transcript request from this server") from exc
    except CouldNotRetrieveTranscript as exc:
        raise IngestionError("Could not retrieve a transcript for that video") from exc

    cues = tuple(
        (snippet.text.strip(), float(snippet.start), float(snippet.start + snippet.duration))
        for snippet in fetched
        if snippet.text.strip()
    )

    if not cues:
        raise IngestionError("No transcript text found for that video")

    return VideoTranscript(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=_fetch_title(video_id),
        cues=cues,
    )

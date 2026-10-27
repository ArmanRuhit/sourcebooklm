"""Fetch and extract readable text from a public web page.

WebBaseLoader handles the HTML-to-text pass; this module adds the safety checks
the loader deliberately leaves to the caller (public-host validation, timeout,
and a stable error surface for the worker).
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from langchain_community.document_loaders import WebBaseLoader

from app.services.ingestion.errors import IngestionError

FETCH_TIMEOUT_SECONDS = 15
USER_AGENT = "SourcebookLM/0.1 (+https://sourcebooklm.app)"
MAX_DESCRIPTION_LENGTH = 500


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

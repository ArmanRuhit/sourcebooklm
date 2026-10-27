"""PDF extractor tests: page numbering, text, and clear failures."""

import pytest

from app.services.ingestion.errors import IngestionError
from app.services.ingestion.pdf import extract_pages
from tests.pdf_fixture import make_pdf


def test_extract_pages_keeps_page_numbers() -> None:
    pages = extract_pages(make_pdf(["Hello first page", "Second page text"]))

    assert [page["page"] for page in pages] == [1, 2]
    assert "Hello first page" in pages[0]["text"]
    assert "Second page text" in pages[1]["text"]


def test_extract_rejects_corrupt_pdf() -> None:
    with pytest.raises(IngestionError, match="Could not read PDF"):
        extract_pages(b"this is not a pdf")


def test_extract_rejects_pdf_without_text() -> None:
    with pytest.raises(IngestionError, match="No extractable text"):
        extract_pages(make_pdf([""]))

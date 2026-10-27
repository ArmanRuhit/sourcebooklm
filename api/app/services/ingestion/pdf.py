"""PDF text extraction (technical design §5.3).

The uploaded bytes stay in `source_files`; this module only produces the
per-page snapshot stored in `source_contents.pages`.
"""

from io import BytesIO
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.ingestion.errors import IngestionError


def extract_pages(data: bytes) -> list[dict[str, Any]]:
    """Return `[{page, text}]` for every page, numbered from 1.

    Raises `IngestionError` with a user-facing message when the file is not a
    readable, unencrypted PDF or contains no selectable text.
    """
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise IngestionError("PDF is password-protected")
        pages = [
            {"page": number, "text": (page.extract_text() or "").strip()}
            for number, page in enumerate(reader.pages, start=1)
        ]
    except IngestionError:
        raise
    except (PdfReadError, ValueError, OSError) as exc:
        raise IngestionError("Could not read PDF (the file may be corrupted)") from exc
    except Exception as exc:  # pypdf raises a wide range of parser errors
        raise IngestionError("Could not read PDF (the file may be corrupted)") from exc

    if not any(page["text"] for page in pages):
        raise IngestionError("No extractable text in PDF (scanned PDFs are not supported yet)")
    return pages

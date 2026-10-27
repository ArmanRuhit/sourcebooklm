"""Build tiny, valid PDFs with selectable text for tests.

Avoids binary fixtures and extra dependencies: the objects and xref table are
assembled directly, which is enough for pypdf to read page text.
"""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    """Return a one-font PDF with one line of text per page."""
    font_number = 3 + 2 * len(pages)
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(len(pages)))}] "
            f"/Count {len(pages)} >>"
        ).encode(),
        font_number: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for index, text in enumerate(pages):
        page_number = 3 + 2 * index
        content_number = page_number + 1
        content = f"BT /F1 24 Tf 72 720 Td ({_escape(text)}) Tj ET".encode()
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_number} 0 R >> >> "
            f"/Contents {content_number} 0 R >>"
        ).encode()
        objects[content_number] = (
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    max_number = max(objects)
    xref_offset = len(out)
    out += f"xref\n0 {max_number + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for number in range(1, max_number + 1):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {max_number + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(out)

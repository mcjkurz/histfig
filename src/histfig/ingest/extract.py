"""Turn uploaded files into plain text."""

from __future__ import annotations

import io
from pathlib import Path

SUPPORTED = {".txt": "txt", ".md": "txt", ".pdf": "pdf", ".docx": "docx"}


class ExtractionError(ValueError):
    pass


def file_type(filename: str) -> str | None:
    return SUPPORTED.get(Path(filename).suffix.lower())


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Unknown legacy encoding (GBK/Big5/cp1252/...): let charset-normalizer guess.
    from charset_normalizer import from_bytes

    results = from_bytes(data)
    best = results.best()
    if best is not None:
        # Short Western texts are ambiguous between cp125x/latin-x code pages;
        # cp1252 is by far the most common, so prefer it whenever it fits.
        latin = best.encoding.startswith(("cp125", "iso8859", "latin", "mac_"))
        cp1252 = next((m for m in results if m.encoding == "cp1252"), None)
        return str(cp1252 if latin and cp1252 is not None else best)
    return data.decode("utf-8", errors="replace")


def extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as e:  # pypdf raises many exception types
        raise ExtractionError(f"Could not read PDF: {e}") from e
    return "\n\n".join(p for p in pages if p)


def extract_docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise ExtractionError(f"Could not read DOCX: {e}") from e
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def extract_text(data: bytes, kind: str) -> str:
    if kind == "txt":
        text = decode_text(data)
    elif kind == "pdf":
        text = extract_pdf(data)
    elif kind == "docx":
        text = extract_docx(data)
    else:
        raise ExtractionError(f"Unsupported file type: {kind}")
    text = text.replace("\x00", "")
    if not text.strip():
        hint = " (scanned PDFs need OCR first)" if kind == "pdf" else ""
        raise ExtractionError(f"No text could be extracted{hint}.")
    return text

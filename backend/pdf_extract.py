"""Extract text from invoice PDF attachments for AI analysis."""
from __future__ import annotations

import io
import logging

logger = logging.getLogger("scotive.pdf")

MAX_PDF_CHARS = 8000
MAX_PAGES = 6


def extract_pdf_text(data: bytes, *, max_chars: int = MAX_PDF_CHARS) -> str:
    if not data:
        return ""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pdf SKIP reason=pypdf_not_installed")
        return ""

    try:
        reader = PdfReader(io.BytesIO(data))
        chunks: list[str] = []
        for page in reader.pages[:MAX_PAGES]:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text.strip())
        out = "\n\n".join(chunks)
        return out[:max_chars]
    except Exception as e:
        logger.warning("pdf EXTRACT_FAIL err=%s", e)
        return ""


def is_pdf_part(part: dict) -> bool:
    fn = (part.get("filename") or "").lower()
    mime = (part.get("mime_type") or "").lower()
    return fn.endswith(".pdf") or mime == "application/pdf"

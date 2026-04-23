"""
Import financial PDF documents using pdfplumber.

Text extraction handles both raw text and tables (common in advisor plan PDFs
that show asset allocations, projections, etc.).
"""
import hashlib
import logging
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pdfplumber

import db

logger = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 60_000
_DOC_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["plan", "proposal", "advisor", "strategy", "portfolio"], "financial_plan"),
    (["1099", "w-2", "w2", "k-1", "tax"], "tax_doc"),
    (["statement", "account", "schwab", "fidelity", "vanguard", "brokerage"], "statement"),
]


def _infer_doc_type(filename: str) -> str:
    lower = filename.lower()
    for keywords, doc_type in _DOC_TYPE_KEYWORDS:
        if any(k in lower for k in keywords):
            return doc_type
    return "other"


def _format_table(table: list[list]) -> str:
    """Convert a pdfplumber table (list of rows) to a plain-text representation."""
    buf = StringIO()
    for row in table:
        cells = [str(c or "").strip() for c in row]
        buf.write(" | ".join(cells) + "\n")
    return buf.getvalue()


def _make_id(path: Path) -> str:
    size = path.stat().st_size
    raw = f"{path.name}|{size}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def import_file(path: Path) -> bool:
    """
    Extract text from a PDF and store it in the documents table.
    Returns True if newly imported, False if already present.
    """
    doc_id = _make_id(path)
    conn = db.get_connection()

    existing = conn.execute("SELECT id FROM documents WHERE id=?", (doc_id,)).fetchone()
    if existing:
        conn.close()
        logger.info("pdf_importer: already imported %s — skipping", path.name)
        return False

    text_parts: list[str] = []
    page_count = 0

    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                tables = page.extract_tables()
                for table in tables:
                    page_text += "\n" + _format_table(table)
                text_parts.append(page_text)
    except Exception as exc:
        logger.error("pdf_importer: failed to parse %s: %s", path.name, exc)
        conn.close()
        return False

    extracted = "\n\n".join(text_parts)
    if len(extracted) > _MAX_TEXT_CHARS:
        extracted = extracted[:_MAX_TEXT_CHARS] + "\n[truncated]"
        logger.warning("pdf_importer: %s truncated to %d chars", path.name, _MAX_TEXT_CHARS)

    if not extracted.strip():
        logger.warning("pdf_importer: %s yielded no text — may need OCR", path.name)

    doc_type = _infer_doc_type(path.name)
    now = datetime.now(tz=timezone.utc).isoformat()

    conn.execute(
        """INSERT OR IGNORE INTO documents
           (id, filename, doc_type, date_of_doc, extracted_text, page_count, imported_at)
           VALUES (?,?,?,?,?,?,?)""",
        (doc_id, path.name, doc_type, None, extracted, page_count, now),
    )
    conn.commit()
    conn.close()

    logger.info("pdf_importer: imported %s (%d pages, type=%s)", path.name, page_count, doc_type)
    return True

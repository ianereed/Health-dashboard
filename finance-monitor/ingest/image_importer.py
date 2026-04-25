"""
Import financial images (receipts, statements, anything visual) via local OCR.

All model calls stay on-device — qwen2.5vl:7b for OCR, qwen3:14b for
structured-field extraction. No cloud fallback. Mirrors the privacy-first
policy of the dispatcher.

Flow:
  1. OCR the image via Ollama vision → extracted_text
  2. If the text looks like a receipt (qwen3 structured probe):
       → insert a row into `transactions` with source='image_import'
     else:
       → insert a row into `documents` (same shape as pdf_importer)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

import config
import db

logger = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 60_000
_LOCAL_VISION_MODEL = "qwen2.5vl:7b"  # must be pulled on the mini's Ollama

# Dispatcher writes a <file>.thread.json sidecar so we can post extraction
# results back to the originating Slack thread. Watcher and importer also use
# the sidecar to track per-file OCR attempts before quarantining.
SIDECAR_SUFFIX = ".thread.json"
MAX_OCR_ATTEMPTS = 3

_OCR_PROMPT = """\
You are an OCR assistant. Extract ALL readable text from this image as plain
text. Preserve amounts, dates, line items, and headings. If the image is
clearly not a document (selfie, meme, etc.), respond with exactly: NOT_A_DOCUMENT.
"""

_RECEIPT_PROBE_PROMPT = """\
Given the following OCR'd text from an image, decide if it represents a
purchase receipt, bill, invoice, or single-transaction record (i.e. one
specific payment/charge). Return ONLY valid JSON:

{{
  "is_receipt": <true|false>,
  "date": "<YYYY-MM-DD if visible, else null>",
  "merchant": "<merchant/payee name, short, else null>",
  "amount": "<total charged as a number, e.g. 42.18; positive for outflows; else null>",
  "account": "<card/account last-4 if visible, else null>",
  "memo": "<one short line describing the purchase, or null>"
}}

Today's date is {today}.

OCR text:
{text}
"""


def import_file(path: Path) -> bool:
    """OCR and ingest an image. Returns True on successful insert, False otherwise.

    Side effects: reads / writes / deletes a sidecar JSON next to the file,
    and posts a single Slack message in-thread when the dispatcher provided
    thread context.
    """
    sidecar = _load_sidecar(path)
    channel = sidecar.get("channel") or ""
    thread_ts = sidecar.get("thread_ts") or ""

    try:
        file_bytes = path.read_bytes()
    except Exception as exc:
        logger.error("image_importer: cannot read %s: %s", path.name, exc)
        return False

    text = _ocr_local(file_bytes, path.name)
    if text is None:
        attempts = int(sidecar.get("attempts") or 0) + 1
        sidecar["attempts"] = attempts
        if not sidecar.get("notified_failure"):
            _post_to_slack(
                channel, thread_ts,
                f":hourglass_flowing_sand: OCR failed for `{path.name}` — will retry next "
                f"5-min tick. Check that `qwen2.5vl:7b` is loaded.",
            )
            sidecar["notified_failure"] = True
        _save_sidecar(path, sidecar)
        logger.warning(
            "image_importer: OCR failed for %s (attempt %d/%d) — Ollama unreachable or model missing",
            path.name, attempts, MAX_OCR_ATTEMPTS,
        )
        return False

    if text.strip().upper() == "NOT_A_DOCUMENT" or len(text.strip()) < 10:
        logger.info("image_importer: %s looks non-textual — leaving as document", path.name)
        ok = _insert_document(path, text, file_bytes)
        if ok:
            _post_to_slack(
                channel, thread_ts,
                f":grey_question: `{path.name}` doesn't look like a document — saved as `image_other`.",
            )
            _remove_sidecar(path)
        return ok

    receipt = _probe_receipt(text)
    if receipt and receipt.get("is_receipt") and receipt.get("date") and receipt.get("amount") is not None:
        ok = _insert_transaction(path, receipt, memo_text=text[:500])
        if ok:
            _post_to_slack(channel, thread_ts, _format_receipt_message(receipt))
            _remove_sidecar(path)
        return ok

    ok = _insert_document(path, text, file_bytes)
    if ok:
        _post_to_slack(
            channel, thread_ts,
            f":page_facing_up: Saved `{path.name}` as a document — couldn't extract a "
            f"date and amount, so it's not booked as a transaction.",
        )
        _remove_sidecar(path)
    return ok


def quarantine(file_path: Path) -> None:
    """Move a file (and its sidecar) into intake/quarantine/ after exhausting
    OCR retries; post a one-time Slack notice if we have thread context.
    """
    sidecar = _load_sidecar(file_path)
    channel = sidecar.get("channel") or ""
    thread_ts = sidecar.get("thread_ts") or ""

    qdir = config.INTAKE_DIR / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)

    target = qdir / file_path.name
    try:
        file_path.rename(target)
    except OSError as exc:
        logger.error("image_importer: quarantine move failed for %s: %s", file_path.name, exc)
        return

    sc = _sidecar_path(file_path)
    if sc.exists():
        try:
            sc.rename(qdir / sc.name)
        except OSError:
            pass

    logger.error(
        "image_importer: %s quarantined after %d failed OCR attempts",
        file_path.name, MAX_OCR_ATTEMPTS,
    )
    _post_to_slack(
        channel, thread_ts,
        f":warning: `{file_path.name}` quarantined after {MAX_OCR_ATTEMPTS} failed OCR "
        f"attempts. Inspect at `intake/quarantine/`.",
    )


def get_attempts(file_path: Path) -> int:
    """How many times has OCR failed on this file? Used by the watcher to decide
    when to quarantine."""
    return int(_load_sidecar(file_path).get("attempts") or 0)


# ── Sidecar helpers ──────────────────────────────────────────────────────────

def _sidecar_path(file_path: Path) -> Path:
    return file_path.with_name(file_path.name + SIDECAR_SUFFIX)


def _load_sidecar(file_path: Path) -> dict:
    p = _sidecar_path(file_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_sidecar(file_path: Path, data: dict) -> None:
    p = _sidecar_path(file_path)
    try:
        p.write_text(json.dumps(data))
    except OSError as exc:
        logger.warning("image_importer: failed to write sidecar %s: %s", p, exc)


def _remove_sidecar(file_path: Path) -> None:
    p = _sidecar_path(file_path)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


# ── Slack callback ───────────────────────────────────────────────────────────

def _post_to_slack(channel: str, thread_ts: str, text: str) -> bool:
    """Best-effort thread reply. Silent no-op if context or token missing."""
    if not channel or not thread_ts:
        return False
    if not config.SLACK_BOT_TOKEN:
        logger.debug("image_importer: no SLACK_BOT_TOKEN — skipping callback")
        return False
    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"channel": channel, "thread_ts": thread_ts, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
        if not resp.json().get("ok", False):
            logger.warning("image_importer: Slack callback not-ok: %s", resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("image_importer: Slack callback failed: %s", exc)
        return False


def _format_receipt_message(receipt: dict) -> str:
    merchant = (receipt.get("merchant") or "(unknown)").strip() or "(unknown)"
    try:
        amount = float(receipt.get("amount") or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    date_str = str(receipt.get("date") or "")[:10]
    account = (receipt.get("account") or "").strip()
    account_note = f" _(account: ****{account})_" if account else ""
    return f":moneybag: Booked: *{merchant}* — ${amount:.2f} on {date_str}{account_note}"


# ── OCR ──────────────────────────────────────────────────────────────────────

def _ocr_local(file_bytes: bytes, filename: str) -> str | None:
    """Single-page OCR via local Ollama vision. Returns the extracted text, or None."""
    b64 = base64.standard_b64encode(file_bytes).decode("ascii")
    try:
        resp = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": _LOCAL_VISION_MODEL,
                "prompt": _OCR_PROMPT,
                "images": [b64],
                "stream": False,
                "keep_alive": "10s",
                "think": False,
                "options": {"temperature": 0.1},
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as exc:
        logger.debug("image_importer: OCR error for %s: %s", filename, exc)
        return None


def _probe_receipt(text: str) -> dict | None:
    """Ask qwen3 whether the OCR'd text looks like a receipt; extract fields."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snippet = text[:4000]
    prompt = _RECEIPT_PROBE_PROMPT.format(today=today, text=snippet)
    try:
        resp = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "10s",
                "think": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return json.loads(resp.json().get("response", ""))
    except Exception as exc:
        logger.debug("image_importer: receipt probe error: %s", exc)
        return None


# ── Inserts ──────────────────────────────────────────────────────────────────

def _insert_transaction(path: Path, receipt: dict, memo_text: str) -> bool:
    """Insert a single transaction row sourced from an image receipt."""
    try:
        amount = float(receipt.get("amount") or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount == 0.0:
        logger.info("image_importer: %s receipt amount missing — falling back to document", path.name)
        return _insert_document(path, memo_text, None)

    date = str(receipt.get("date") or "")[:10]
    merchant = (receipt.get("merchant") or path.stem)[:120]
    account = (receipt.get("account") or "image_import")[:80]
    memo = (receipt.get("memo") or "")[:400]

    txn_id = hashlib.sha256(f"img|{path.name}|{date}|{merchant}|{amount:.2f}".encode()).hexdigest()[:32]
    now = datetime.now(tz=timezone.utc).isoformat()

    conn = db.get_connection()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO transactions
               (id, date, payee, outflow, inflow, amount, category, account, memo, cleared,
                is_transfer, source, raw_file, imported_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                txn_id,
                date,
                merchant,
                amount if amount > 0 else 0.0,
                -amount if amount < 0 else 0.0,
                -amount,  # outflow is positive in YNAB convention → amount is negative
                None,
                account,
                memo,
                "uncleared",
                0,
                "image_import",
                path.name,
                now,
            ),
        )
        conn.commit()
        inserted = cur.rowcount > 0
    finally:
        conn.close()

    if inserted:
        logger.info("image_importer: transaction %s | %s %s (%.2f)", path.name, date, merchant, amount)
    else:
        # INSERT OR IGNORE: row already exists (re-uploaded image with the same
        # date/merchant/amount). Treat as success so the watcher moves the file
        # out of intake/ rather than retrying forever.
        logger.info("image_importer: transaction %s already present — skipping insert", path.name)
    return True


def _insert_document(path: Path, text: str, file_bytes: bytes | None) -> bool:
    """Insert a document row (mirrors pdf_importer)."""
    # Use content hash so dups get ignored.
    raw = file_bytes if file_bytes is not None else text.encode("utf-8", errors="replace")
    doc_id = hashlib.sha256(raw + path.name.encode()).hexdigest()[:32]

    trimmed = text if len(text) <= _MAX_TEXT_CHARS else text[:_MAX_TEXT_CHARS] + "\n[truncated]"
    if len(trimmed) != len(text):
        logger.warning("image_importer: %s truncated to %d chars", path.name, _MAX_TEXT_CHARS)

    doc_type = _infer_doc_type(path.name, text)
    now = datetime.now(tz=timezone.utc).isoformat()

    conn = db.get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO documents
               (id, filename, doc_type, date_of_doc, extracted_text, page_count, imported_at)
               VALUES (?,?,?,?,?,?,?)""",
            (doc_id, path.name, doc_type, None, trimmed, 1, now),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("image_importer: document %s (type=%s)", path.name, doc_type)
    return True


_IMAGE_DOC_KEYWORDS: list[tuple[list[str], str]] = [
    (["statement", "balance", "account", "schwab", "fidelity", "vanguard", "brokerage", "chase"], "statement"),
    (["invoice", "bill", "due"], "invoice"),
    (["receipt", "total", "subtotal"], "receipt"),
    (["1099", "w-2", "w2", "k-1", "tax"], "tax_doc"),
]


def _infer_doc_type(filename: str, text: str) -> str:
    blob = (filename + " " + text[:2000]).lower()
    for keywords, doc_type in _IMAGE_DOC_KEYWORDS:
        if any(k in blob for k in keywords):
            return doc_type
    return "image_other"

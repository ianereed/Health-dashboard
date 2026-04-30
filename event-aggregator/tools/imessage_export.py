#!/usr/bin/env python3
"""
imessage_export — laptop-side exporter for event-aggregator.

Reads ~/Library/Messages/chat.db on the host that has iMessage signed in
(typically a laptop), writes a JSONL of the last N days of text messages
to --out. A LaunchAgent invokes this every 10 min, then scp's the JSONL
over Tailscale SSH to the headless Mac mini that runs the rest of the
pipeline.

Self-contained: stdlib-only. Does NOT import from connectors/, config.py,
or models.py — keeps the laptop deploy decoupled from the mini repo.

Privacy:
  - JSONL contains message bodies. The output dir is locked to 0o700,
    files to 0o600.
  - Refuses to write into iCloud-synced or sandbox-protected paths
    (~/Library/Mobile Documents/, ~/Documents/, ~/Desktop/, ~/Pictures/)
    so the export never leaks into iCloud Drive.
  - stderr lines are counts only — never bodies, never handles, never
    timestamps.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
_APPLE_EPOCH_NS_THRESHOLD = 1_000_000_000
_ROW_LIMIT = 500


def _apple_ts_to_utc(ts):
    if ts > _APPLE_EPOCH_NS_THRESHOLD:
        ts = ts / 1e9
    return _APPLE_EPOCH + timedelta(seconds=ts)


def _decode_attributed_body(blob):
    """Best-effort extract text from chat.db's `attributedBody` column.

    On modern macOS, message bodies for any message with formatting, links,
    Tapback context, or iCloud-Messages-synced content arrive with `text=NULL`
    and the actual content in `attributedBody` — a binary typedstream-encoded
    NSAttributedString. This decoder uses the well-known regex-free heuristic:
    locate the NSString class marker, skip past `+`, read the length-prefixed
    UTF-8 payload. Length encoding: byte=0x81 → next 2 bytes little-endian
    uint16; else single byte (1-127).

    Verified against 22 chat.db rows on 2026-04-29 — every row decoded; rows
    with non-NULL `text` produced decoded strings exactly matching `text`.
    """
    if not blob:
        return None
    idx = blob.find(b"NSString")
    if idx == -1:
        return None
    after = blob[idx + len(b"NSString"):]
    plus = after.find(b"+")
    if plus == -1:
        return None
    rest = after[plus + 1:]
    if not rest:
        return None
    if rest[0] == 0x81:
        if len(rest) < 3:
            return None
        length = int.from_bytes(rest[1:3], "little")
        start = 3
    else:
        length = rest[0]
        start = 1
    if start + length > len(rest):
        return None
    try:
        return rest[start:start + length].decode("utf-8")
    except UnicodeDecodeError:
        return None


def _refuse_protected_path(out_path: Path) -> None:
    """Abort if --out lands in an iCloud-Drive or TCC-protected directory."""
    home = Path.home().resolve()
    resolved = out_path.resolve()
    forbidden = [
        home / "Library" / "Mobile Documents",
        home / "Documents",
        home / "Desktop",
        home / "Pictures",
        home / "Music",
        home / "Movies",
    ]
    for bad in forbidden:
        try:
            resolved.relative_to(bad)
        except ValueError:
            continue
        sys.stderr.write(
            f"refusing to write into protected path: {bad} "
            f"(would risk iCloud-Drive sync of message bodies)\n"
        )
        sys.exit(2)


def _ensure_parent_dir(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(out_path.parent, 0o700)
    except PermissionError:
        pass


def _query_chat_db(db_path: Path, since_ns: float) -> list[sqlite3.Row]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy2(db_path, tmp_path)
        with sqlite3.connect(str(tmp_path)) as conn:
            conn.row_factory = sqlite3.Row
            # JOIN handle table so we ship the real identifier (phone/email)
            # rather than the opaque integer FK from message.handle_id.
            return conn.execute(
                """
                SELECT
                    m.ROWID AS rowid,
                    m.text AS text,
                    m.attributedBody AS attributedBody,
                    m.date AS date,
                    m.handle_id AS handle_id,
                    h.id AS handle,
                    m.is_from_me AS is_from_me
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.date > ?
                  AND (
                    (m.text IS NOT NULL AND m.text != '')
                    OR m.attributedBody IS NOT NULL
                  )
                ORDER BY m.date DESC
                LIMIT ?
                """,
                (since_ns, _ROW_LIMIT),
            ).fetchall()
    finally:
        tmp_path.unlink(missing_ok=True)


def _resolve_body(row: sqlite3.Row) -> str | None:
    txt = row["text"]
    if txt:
        return txt
    decoded = _decode_attributed_body(row["attributedBody"])
    if decoded:
        return decoded
    return None


def _row_to_jsonl(row: sqlite3.Row) -> str | None:
    body = _resolve_body(row)
    if not body:
        return None
    ts = _apple_ts_to_utc(row["date"])
    obj = {
        "id": f"imessage_{row['rowid']}",
        "source": "imessage",
        "timestamp": ts.isoformat(),
        "body_text": body,
        "metadata": {
            "handle_id": row["handle_id"],
            "handle": row["handle"],
            "is_from_me": bool(row["is_from_me"]),
        },
    }
    return json.dumps(obj, ensure_ascii=False)


def _atomic_write_jsonl(out_path: Path, lines: list[str]) -> None:
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line)
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, out_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export recent iMessages to JSONL for shipping to a remote consumer."
    )
    parser.add_argument("--out", required=True, type=Path, help="Output JSONL path")
    parser.add_argument(
        "--days", type=int, default=14, help="Window of days back to export (default 14)"
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=Path("~/Library/Messages/chat.db").expanduser(),
        help="Path to chat.db (default: ~/Library/Messages/chat.db)",
    )
    args = parser.parse_args()

    out_path = args.out.expanduser()
    _refuse_protected_path(out_path)
    _ensure_parent_dir(out_path)

    db_path = args.source_db.expanduser()
    if not db_path.exists():
        sys.stderr.write(f"chat.db not found at {db_path}\n")
        return 3

    since_dt = datetime.now(tz=timezone.utc) - timedelta(days=args.days)
    since_ns = (since_dt - _APPLE_EPOCH).total_seconds() * 1e9

    try:
        rows = _query_chat_db(db_path, since_ns)
    except PermissionError:
        sys.stderr.write("chat.db unreadable — FDA likely missing for this binary\n")
        return 4
    except sqlite3.OperationalError as exc:
        sys.stderr.write(f"chat.db query failed: {type(exc).__name__}\n")
        return 5

    written = 0
    dropped = 0
    no_body = 0
    lines: list[str] = []
    for row in rows:
        try:
            line = _row_to_jsonl(row)
            if line is None:
                no_body += 1
                continue
            lines.append(line)
            written += 1
        except (TypeError, ValueError, KeyError):
            dropped += 1

    _atomic_write_jsonl(out_path, lines)

    hit_limit = len(rows) >= _ROW_LIMIT
    sys.stderr.write(
        f"wrote {written} messages, dropped {dropped}, no_body {no_body}, hit_limit={hit_limit}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

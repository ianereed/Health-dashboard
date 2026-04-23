"""
Parse YNAB register CSV exports and import transactions into SQLite.

YNAB export columns (from web app → All Accounts → Export):
  Account, Flag, Date, Payee, Category Group/Category, Category Group,
  Category, Memo, Outflow, Inflow, Cleared

Date format: MM/DD/YYYY
Amount format: may include $ and , (e.g. "$1,234.56")
Transfers: Payee starts with "Transfer : " — excluded from spending queries.
"""
import csv
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import db

logger = logging.getLogger(__name__)

_CURRENCY_RE = re.compile(r"[$,]")


def _parse_amount(s: str) -> float:
    return float(_CURRENCY_RE.sub("", s.strip()) or "0")


def _parse_date(s: str) -> str:
    """MM/DD/YYYY → YYYY-MM-DD."""
    return datetime.strptime(s.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")


def _make_id(account: str, date: str, payee: str, outflow: float, inflow: float) -> str:
    raw = f"{account}|{date}|{payee}|{outflow:.4f}|{inflow:.4f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def import_file(path: Path) -> tuple[int, int]:
    """
    Import a YNAB register CSV. Returns (imported, skipped) counts.
    Skipped means already present in DB (idempotent re-import).
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    conn = db.get_connection()
    imported = 0
    skipped = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                date = _parse_date(row["Date"])
                payee = row.get("Payee", "").strip()
                account = row.get("Account", "").strip()
                category = row.get("Category Group/Category", "").strip() or None
                memo = row.get("Memo", "").strip() or None
                cleared = row.get("Cleared", "").strip() or None
                outflow = _parse_amount(row.get("Outflow", "0"))
                inflow = _parse_amount(row.get("Inflow", "0"))
                amount = inflow - outflow
                is_transfer = 1 if payee.startswith("Transfer :") else 0
                txn_id = _make_id(account, date, payee, outflow, inflow)
            except (KeyError, ValueError) as exc:
                logger.warning("ynab_csv: skipping malformed row: %s", exc)
                continue

            cur = conn.execute(
                """INSERT OR IGNORE INTO transactions
                   (id, date, payee, outflow, inflow, amount, category, account,
                    memo, cleared, is_transfer, source, raw_file, imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (txn_id, date, payee, outflow, inflow, amount, category, account,
                 memo, cleared, is_transfer, "ynab_csv", path.name, now),
            )
            if cur.rowcount:
                imported += 1
            else:
                skipped += 1

    conn.commit()
    conn.close()
    logger.info("ynab_csv: %s → imported=%d skipped=%d", path.name, imported, skipped)
    return imported, skipped

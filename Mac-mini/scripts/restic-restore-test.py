#!/usr/bin/env python3
"""Phase 7 backup integrity verification.

Restores the latest health.db snapshot from the hourly repo to /tmp,
checks size + sha256 + SQLite PRAGMA integrity_check. The sha256 may
differ from the live file if the live DB was written between snapshot
and now — that's fine. The integrity_check is the load-bearing assertion:
restic captured a consistent enough WAL state to reopen the DB cleanly.

Exit 0 = pass. Exit 1 = fail.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(os.environ["HOME"])
BACKUP_ROOT = HOME / "Share1" / "mac-mini-backups"
KEYCHAIN_PATH = os.environ.get(
    "KEYCHAIN_PATH",
    str(HOME / "Library" / "Keychains" / "login.keychain-db"),
)
HEALTH_DB = HOME / "Home-Tools" / "health-dashboard" / "data" / "health.db"
HOURLY_REPO = BACKUP_ROOT / "restic-hourly"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    subprocess.run(
        ["security", "unlock-keychain", "-p", "", KEYCHAIN_PATH],
        capture_output=True, check=False,
    )

    p = subprocess.run(
        [
            "security", "find-generic-password",
            "-s", "restic-hourly-backup", "-a", "password", "-w", KEYCHAIN_PATH,
        ],
        capture_output=True, text=True, check=False,
    )
    if p.returncode != 0:
        print(f"ERROR: keychain lookup failed: {p.stderr.strip()}", flush=True)
        return 1
    password = p.stdout.strip()

    if not HOURLY_REPO.exists():
        print(f"ERROR: hourly repo not found at {HOURLY_REPO}", flush=True)
        return 1

    if not HEALTH_DB.exists():
        print(f"WARN: live health.db not present at {HEALTH_DB}, skipping live-comparison", flush=True)

    with tempfile.TemporaryDirectory(prefix="restic-restore-test-") as tmp:
        tmp_path = Path(tmp)
        env = os.environ.copy()
        env["RESTIC_REPOSITORY"] = str(HOURLY_REPO)
        env["RESTIC_PASSWORD"] = password

        r = subprocess.run(
            ["restic", "restore", "latest", "--target", str(tmp_path)],
            env=env, capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            print(f"ERROR: restic restore failed (exit {r.returncode})", flush=True)
            if r.stderr:
                print(f"  stderr: {r.stderr[:500]}", flush=True)
            return 1

        # Locate the restored health.db (preserves absolute path under target).
        candidates = list(tmp_path.rglob("health.db"))
        if not candidates:
            print(f"ERROR: restored health.db not found in {tmp_path}", flush=True)
            return 1
        restored = candidates[0]

        restored_size = restored.stat().st_size
        print(f"restored: {restored} ({restored_size:,} bytes)", flush=True)

        if HEALTH_DB.exists():
            live_size = HEALTH_DB.stat().st_size
            live_hash = sha256(HEALTH_DB)
            restored_hash = sha256(restored)
            match_label = "MATCH" if live_hash == restored_hash else "DIFFER (expected — live may have changed)"
            print(f"live size: {live_size:,}  sha256 {match_label}", flush=True)
            print(f"  live:     {live_hash[:32]}...", flush=True)
            print(f"  restored: {restored_hash[:32]}...", flush=True)

        # Load-bearing assertion: restored DB opens cleanly.
        try:
            conn = sqlite3.connect(f"file:{restored}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            result = cur.fetchall()
            conn.close()
        except sqlite3.Error as e:
            print(f"integrity_check: SQLite error — {e}", flush=True)
            return 1

        if result == [("ok",)]:
            print("integrity_check: PASS", flush=True)
            return 0
        print(f"integrity_check: FAIL — {result}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

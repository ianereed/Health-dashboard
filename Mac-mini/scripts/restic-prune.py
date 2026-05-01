#!/usr/bin/env python3
"""Weekly restic prune for both Phase 7 backup repos.

Runs `restic prune` against restic-hourly and restic-daily sequentially.
Prune is heavier than backup (rewrites pack files); weekly cadence keeps
disk reclaim ~timely without burning I/O hourly. `forget` runs per-backup
in restic-backup.py; prune just collects unreferenced data.

Scheduled via com.home-tools.restic-prune.plist (Sun 04:00).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ["HOME"])
BACKUP_ROOT = HOME / "Share1" / "mac-mini-backups"
RUN_DIR = HOME / "Home-Tools" / "run"
LOGS_DIR = HOME / "Home-Tools" / "logs"
INCIDENTS_FILE = LOGS_DIR / "incidents.jsonl"
KEYCHAIN_PATH = os.environ.get(
    "KEYCHAIN_PATH",
    str(HOME / "Library" / "Keychains" / "login.keychain-db"),
)

REPOS = {
    "hourly": (BACKUP_ROOT / "restic-hourly", "restic-hourly-backup"),
    "daily": (BACKUP_ROOT / "restic-daily", "restic-daily-backup"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_event(event: dict) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with INCIDENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    print(f"restic-prune ts={now_iso()}", flush=True)

    subprocess.run(
        ["security", "unlock-keychain", "-p", "", KEYCHAIN_PATH],
        capture_output=True, check=False,
    )

    overall_rc = 0
    for label, (repo_dir, kc_service) in REPOS.items():
        if not repo_dir.exists():
            print(f"prune {label}: repo missing at {repo_dir}, skipping", flush=True)
            continue

        p = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", kc_service, "-a", "password", "-w", KEYCHAIN_PATH,
            ],
            capture_output=True, text=True, check=False,
        )
        if p.returncode != 0:
            print(f"prune {label}: keychain lookup failed: {p.stderr.strip()}", flush=True)
            overall_rc = 1
            append_event({
                "ts": now_iso(),
                "kind": "prune_failed",
                "key": f"backup:{label}",
                "reason": "keychain",
            })
            continue
        password = p.stdout.strip()

        env = os.environ.copy()
        env["RESTIC_REPOSITORY"] = str(repo_dir)
        env["RESTIC_PASSWORD"] = password

        t0 = time.time()
        r = subprocess.run(
            ["restic", "prune"],
            env=env, capture_output=True, text=True, check=False,
        )
        dt = time.time() - t0

        if r.returncode != 0:
            print(f"prune {label}: FAILED (exit {r.returncode}, {dt:.1f}s)", flush=True)
            if r.stderr:
                print(f"  stderr: {r.stderr[:300]}", flush=True)
            overall_rc = 1
            append_event({
                "ts": now_iso(),
                "kind": "prune_failed",
                "key": f"backup:{label}",
                "reason": "restic_error",
                "exit": r.returncode,
            })
        else:
            # Print last few lines (restic prune summary).
            summary = [ln for ln in r.stdout.splitlines() if ln.strip()][-3:]
            for ln in summary:
                print(f"  {ln}", flush=True)
            print(f"prune {label}: ok ({dt:.1f}s)", flush=True)

    return overall_rc


if __name__ == "__main__":
    sys.exit(main())

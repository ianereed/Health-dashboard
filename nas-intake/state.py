"""Local state for the watcher: stability gate + dedup.

Two structures persisted in state.json (LOCAL on the mini, NOT on NAS):
- seen[path] = [size, mtime] — for two-tick stability gate
- processed_sha256[] — LRU list capped at DEDUP_HISTORY (most-recent-first)

Atomic save: write to .tmp, os.replace.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class State:
    def __init__(self, path: Path = config.STATE_PATH) -> None:
        self.path = path
        self.seen: dict[str, list[float]] = {}
        self.processed_sha256: list[str] = []

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.seen = dict(data.get("seen", {}))
            self.processed_sha256 = list(data.get("processed_sha256", []))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("state.load: %s; starting empty", exc)
            self.seen, self.processed_sha256 = {}, []

    def save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({
            "seen": self.seen,
            "processed_sha256": self.processed_sha256,
        }, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ── stability gate ─────────────────────────────────────────────────
    def stable_key(self, p: Path) -> tuple[int, float] | None:
        """Return (size, mtime) if file looks stable, else None."""
        try:
            st = p.stat()
            return (st.st_size, st.st_mtime)
        except OSError:
            return None

    def stability_check(self, p: Path) -> str:
        """Returns 'first_sighting' | 'stable' | 'changed' | 'unreadable'.

        - first_sighting: not in seen → record + skip this tick
        - stable: same (size, mtime) as last seen → OK to process
        - changed: differs from last seen → re-record + skip (still uploading)
        - unreadable: stat failed → skip
        """
        cur = self.stable_key(p)
        if cur is None:
            return "unreadable"
        key = str(p)
        prev = self.seen.get(key)
        if prev is None:
            self.seen[key] = list(cur)
            return "first_sighting"
        if list(cur) == list(prev):
            return "stable"
        self.seen[key] = list(cur)
        return "changed"

    def forget(self, p: Path) -> None:
        self.seen.pop(str(p), None)

    # ── dedup ──────────────────────────────────────────────────────────
    def is_processed(self, sha: str) -> bool:
        return sha in self.processed_sha256

    def remember(self, sha: str) -> None:
        if sha in self.processed_sha256:
            return
        self.processed_sha256.insert(0, sha)
        if len(self.processed_sha256) > config.DEDUP_HISTORY:
            del self.processed_sha256[config.DEDUP_HISTORY:]

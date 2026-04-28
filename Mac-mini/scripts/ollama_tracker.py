#!/usr/bin/env python3
"""Ollama load-history tracker.

Runs as a launchd KeepAlive agent (com.home-tools.ollama-tracker.plist).
Every 60s polls /api/ps and writes a small JSON file recording each
model's most recent load timestamp + currently-loaded flag.

Output schema (~/Library/Application Support/home-tools/ollama_history.json):
{
  "models": {
    "qwen3:14b": {
      "size_bytes": 10885037088,
      "last_loaded_at": "2026-04-28T20:30:00+00:00",
      "expires_at": "2318-08-08T13:28:08-07:00"
    },
    ...
  },
  "currently_loaded": ["qwen3:14b"],
  "updated_at": "2026-04-28T20:31:30+00:00"
}

`last_loaded_at` is the FIRST-observed-load timestamp during a
continuous loaded window — i.e., a model that stays resident across
many polls keeps its original load timestamp. A poll cycle that sees
the model absent then present again is a new load.

`expires_at` (if present) lets a debugger distinguish a pinned model
(keep_alive=-1 → far-future date) from a transient one.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

POLL_URL = "http://127.0.0.1:11434/api/ps"
POLL_INTERVAL_SEC = 60
STATE_DIR = Path("~/Library/Application Support/home-tools").expanduser()
STATE_PATH = STATE_DIR / "ollama_history.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s ollama-tracker: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"models": {}, "currently_loaded": [], "updated_at": None}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception as exc:
        logger.warning("state read failed (%s); starting fresh", type(exc).__name__)
        return {"models": {}, "currently_loaded": [], "updated_at": None}


def _cleanup_orphan_tmp_files() -> None:
    """Remove any leftover .tmp files from a prior crashed save."""
    if not STATE_DIR.exists():
        return
    for orphan in STATE_DIR.glob("*.tmp"):
        try:
            orphan.unlink()
        except Exception:
            pass


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=STATE_DIR, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(state, tmp, indent=2)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, STATE_PATH)


def _poll_once(state: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        resp = requests.get(POLL_URL, timeout=3)
        resp.raise_for_status()
        loaded = resp.json().get("models", [])
    except Exception as exc:
        logger.warning("poll failed: %s", type(exc).__name__)
        return

    prev_loaded = set(state.get("currently_loaded", []))
    cur_loaded = []
    for m in loaded:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        cur_loaded.append(name)
        bucket = state["models"].setdefault(
            name, {"size_bytes": 0, "last_loaded_at": None, "expires_at": None},
        )
        bucket["size_bytes"] = (
            m.get("size_vram") or m.get("size") or bucket["size_bytes"]
        )
        bucket["expires_at"] = m.get("expires_at") or bucket.get("expires_at")
        if name not in prev_loaded:
            bucket["last_loaded_at"] = now

    state["currently_loaded"] = cur_loaded
    state["updated_at"] = now


def main() -> int:
    logger.info("starting; state file at %s", STATE_PATH)
    _cleanup_orphan_tmp_files()
    state = _load_state()
    while True:
        _poll_once(state)
        try:
            _save_state(state)
        except Exception as exc:
            logger.warning("save failed: %s", type(exc).__name__)
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    sys.exit(main() or 0)

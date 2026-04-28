#!/usr/bin/env python3
"""Memory/RAM tracker for the Mac mini.

Runs as a launchd KeepAlive agent (com.home-tools.memory-tracker.plist).
Every 60s parses `vm_stat` + `sysctl hw.memsize hw.pagesize`, computes
total/used/available memory matching macOS Activity Monitor's "Memory
Used" line, and writes a JSON state file.

Output schema (~/Library/Application Support/home-tools/memory_history.json):
{
  "current": {
    "total_bytes": 25769803776,
    "used_bytes": 18253611008,
    "available_bytes": 7516192768,
    "percent_used": 70.83,
    "available_pct": 29.17,
    "sampled_at": "2026-04-28T21:30:00+00:00"
  },
  "samples": [
    {"t": "2026-04-28T20:30:00+00:00", "pct": 68.2, "used_gb": 17.6,
     "ollama_loaded": ["qwen3:14b"]},
    ...  // last 1440 entries (24 h at 1-min cadence)
  ],
  "pressure_events": [
    {
      "started_at": "2026-04-28T18:30:00+00:00",
      "ended_at": "2026-04-28T18:45:00+00:00",
      "peak_pct": 93.2,
      "peak_used_gb": 22.4,
      "duration_sec": 900,
      "ollama_at_peak": ["qwen3:14b", "qwen2.5vl:7b"]
    }
  ],  // last 100 events
  "in_pressure": false,
  "updated_at": "2026-04-28T21:30:00+00:00"
}

Pressure trigger: `available_pct < 10` (i.e. used > 90% of total).
Each contiguous pressure window is one event; tracker carries
in_pressure=True across polls until it falls back below the threshold.
On startup, in_pressure is loaded from disk so a tracker restart mid-
event doesn't fragment the record.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

POLL_INTERVAL_SEC = 60
PRESSURE_THRESHOLD_PCT = 90.0  # available < 10% → pressure
SAMPLES_MAX = 1440             # 24 h at 1-min cadence
EVENTS_MAX = 100               # last 100 pressure events

STATE_DIR = Path("~/Library/Application Support/home-tools").expanduser()
STATE_PATH = STATE_DIR / "memory_history.json"
OLLAMA_HISTORY_PATH = STATE_DIR / "ollama_history.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s memory-tracker: %(message)s",
)
logger = logging.getLogger(__name__)


def _read_int_sysctl(key: str) -> int:
    out = subprocess.check_output(["sysctl", "-n", key], text=True)
    return int(out.strip())


def _read_vm_stat() -> dict[str, int]:
    """Return {category: pages} from vm_stat output."""
    out = subprocess.check_output(["vm_stat"], text=True)
    pages: dict[str, int] = {}
    for line in out.splitlines():
        m = re.match(r'^"?([^"]+?)"?:\s+(\d+)\.?\s*$', line)
        if m:
            pages[m.group(1).strip()] = int(m.group(2))
    return pages


def _snapshot() -> dict:
    """Build a single memory snapshot. Matches Activity Monitor:
        used     = (active + wired + compressed) * page_size
        available = total - used
    """
    page_size = _read_int_sysctl("hw.pagesize")
    total = _read_int_sysctl("hw.memsize")
    p = _read_vm_stat()
    active = p.get("Pages active", 0)
    wired = p.get("Pages wired down", 0)
    compressed = p.get("Pages occupied by compressor", 0)
    used = (active + wired + compressed) * page_size
    used = min(used, total)  # paranoia clamp
    available = total - used
    percent_used = (used / total) * 100.0
    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "percent_used": round(percent_used, 2),
        "available_pct": round(100.0 - percent_used, 2),
        "sampled_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_ollama_loaded() -> list[str]:
    """Read currently_loaded from the ollama-tracker state file. Returns []
    if the file is missing/corrupt OR if its updated_at is >5 min old
    (stale tracker — don't silently miscorrelate)."""
    if not OLLAMA_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(OLLAMA_HISTORY_PATH.read_text())
        upd = data.get("updated_at")
        if upd:
            try:
                age = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(upd.replace("Z", "+00:00"))).total_seconds()
                if age > 300:
                    return []
            except Exception:
                pass
        return list(data.get("currently_loaded") or [])
    except Exception:
        return []


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"current": None, "samples": [], "pressure_events": [],
                "in_pressure": False, "updated_at": None}
    try:
        s = json.loads(STATE_PATH.read_text())
        s.setdefault("samples", [])
        s.setdefault("pressure_events", [])
        s.setdefault("in_pressure", False)
        return s
    except Exception as exc:
        logger.warning("state read failed (%s); starting fresh", type(exc).__name__)
        return {"current": None, "samples": [], "pressure_events": [],
                "in_pressure": False, "updated_at": None}


def _cleanup_orphan_tmp_files() -> None:
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
    try:
        snap = _snapshot()
    except Exception as exc:
        logger.warning("snapshot failed: %s", type(exc).__name__)
        return

    ollama_loaded = _read_ollama_loaded()
    snap["ollama_loaded"] = ollama_loaded

    state["current"] = snap
    state["updated_at"] = snap["sampled_at"]

    # Append to rolling 24h sample buffer
    state["samples"].append({
        "t": snap["sampled_at"],
        "pct": snap["percent_used"],
        "used_gb": round(snap["used_bytes"] / (1024**3), 2),
        "ollama_loaded": ollama_loaded,
    })
    if len(state["samples"]) > SAMPLES_MAX:
        state["samples"] = state["samples"][-SAMPLES_MAX:]

    # Pressure-event state machine
    pct = snap["percent_used"]
    in_pressure = bool(state.get("in_pressure"))
    if pct >= PRESSURE_THRESHOLD_PCT:
        if not in_pressure:
            state["in_pressure"] = True
            state["pressure_events"].append({
                "started_at": snap["sampled_at"],
                "ended_at": snap["sampled_at"],
                "peak_pct": pct,
                "peak_used_gb": round(snap["used_bytes"] / (1024**3), 2),
                "duration_sec": 0,
                "ollama_at_peak": ollama_loaded,
            })
        else:
            event = state["pressure_events"][-1]
            event["ended_at"] = snap["sampled_at"]
            try:
                start_dt = datetime.fromisoformat(event["started_at"])
                end_dt = datetime.fromisoformat(event["ended_at"])
                event["duration_sec"] = int((end_dt - start_dt).total_seconds())
            except Exception:
                pass
            if pct > event.get("peak_pct", 0):
                event["peak_pct"] = pct
                event["peak_used_gb"] = round(snap["used_bytes"] / (1024**3), 2)
                event["ollama_at_peak"] = ollama_loaded
    else:
        if in_pressure:
            state["in_pressure"] = False  # event already finalized in last poll

    if len(state["pressure_events"]) > EVENTS_MAX:
        state["pressure_events"] = state["pressure_events"][-EVENTS_MAX:]


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

"""Migration of finance-monitor watcher — every 5 min.

Mirrors the original `com.home-tools.finance-monitor-watcher` plist:
runs `main.py watch` from the project directory using the project's
own venv (not the consumer's), because finance-monitor/config.py uses
bare `import config` + `from dotenv import load_dotenv`.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from huey import crontab

from jobs import baseline, huey, migrates_from, requires
from jobs.kinds._internal.migration_verifier import record_fire

logger = logging.getLogger(__name__)

PROJECT = Path(__file__).resolve().parents[2] / "finance-monitor"
VENV_PYTHON = PROJECT / ".venv" / "bin" / "python3"


@huey.periodic_task(crontab(minute="*/5"))
@requires(["db:finance-monitor/data/finance.db", "fs:finance-monitor"])
@baseline(metric="db-mtime:finance-monitor/data/finance.db", divergence_window="6m", cadence="5m")
@migrates_from("com.home-tools.finance-monitor-watcher")
def finance_monitor_watch() -> dict:
    proc = subprocess.run(
        [str(VENV_PYTHON), "main.py", "watch"],
        cwd=str(PROJECT), capture_output=True, text=True, timeout=240,
    )
    record_fire("finance_monitor_watch")
    if proc.returncode != 0:
        logger.warning("finance-monitor-watcher rc=%d stderr=%s", proc.returncode, proc.stderr[:200])
    return {"rc": proc.returncode}

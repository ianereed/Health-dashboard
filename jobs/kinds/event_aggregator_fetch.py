"""Migration of event-aggregator/com.home-tools.event-aggregator.fetch — every 10 min.

Phase 12.5 — first half of the event-aggregator migration. Replaces the
StartInterval=600 LaunchAgent that polls the connector registry and drops
new messages into state.text_queue.

Pattern mirrors `finance_monitor_watch`: uses the project's own venv
because event-aggregator/main.py imports gmail/slack/imessage modules
that aren't in the jobs-consumer venv. Working directory is the project
dir so `import state` and bare `from connectors import ...` resolve.

Baseline: `event-aggregator/run/event-aggregator-fetch.last` is touched
unconditionally at the end of `fetch_only()` (main.py around line 1645).
That file's mtime is the liveness signal; the verifier compares it
against the captured baseline_snapshot during the 72h soak.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from huey import crontab

from jobs import baseline, huey, migrates_from, requires
from jobs.kinds._internal.migration_verifier import record_fire

logger = logging.getLogger(__name__)

PROJECT = Path(__file__).resolve().parents[2] / "event-aggregator"
VENV_PYTHON = PROJECT / ".venv" / "bin" / "python3"


@huey.periodic_task(crontab(minute="*/10"))
@requires(["fs:event-aggregator"])
@baseline(
    metric="file-mtime:event-aggregator/run/event-aggregator-fetch.last",
    divergence_window="12m",
    cadence="10m",
)
@migrates_from("com.home-tools.event-aggregator.fetch")
def event_aggregator_fetch() -> dict:
    proc = subprocess.run(
        [str(VENV_PYTHON), "main.py", "fetch-only"],
        cwd=str(PROJECT), capture_output=True, text=True, timeout=540,
    )
    record_fire("event_aggregator_fetch")
    if proc.returncode != 0:
        logger.warning(
            "event-aggregator-fetch rc=%d stderr=%s",
            proc.returncode, proc.stderr[:200],
        )
    return {"rc": proc.returncode}

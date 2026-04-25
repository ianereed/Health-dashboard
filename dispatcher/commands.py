"""
Interactive command handling for ian-event-aggregator.

The dispatcher parses the first token of each message and shells out to
event-aggregator's CLI subcommands. Keeps all state mutation inside the
event-aggregator project.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "*Available commands:*\n"
    "• `approve` / `approve 1,3` — approve pending proposals (all or specific numbers)\n"
    "• `reject` / `reject 2` — reject pending proposals\n"
    "• `add: <description>` — manual event entry, e.g. `add: dinner with Bryan Sat 7pm`\n"
    "• `status` — show last run, pending count, ollama health\n"
    "• `last run` — show summary of the most recent run\n"
    "• `pending` — list pending proposals\n"
    "• `what's on <timeframe>` — ask about upcoming events, e.g. `what's on friday`\n"
    "• `conflicts <timeframe>` — check for overlaps, e.g. `conflicts this week`\n"
    "• `help` / `?` — show this message\n"
)


@dataclass
class CommandResult:
    ok: bool
    text: str   # slack-formatted reply


def handle(raw_text: str) -> CommandResult | None:
    """Parse and execute a command. Returns None if the message isn't a command."""
    text = (raw_text or "").strip()
    if not text:
        return None

    lower = text.lower()
    first = lower.split(maxsplit=1)[0]
    rest = text[len(first):].strip()

    if first in ("help", "?"):
        return CommandResult(ok=True, text=HELP_TEXT)

    if first == "approve":
        return _ea_cli(["approve", "--nums", rest] if rest else ["approve"])

    if first == "reject":
        return _ea_cli(["reject", "--nums", rest] if rest else ["reject"])

    if first == "status":
        return _ea_cli(["status", "--json"])

    if first == "pending":
        return _ea_cli(["status", "--pending"])

    # Two-token command: "last run"
    if lower.startswith("last run"):
        return _ea_cli(["status", "--last-run"])

    # Two-token command: "what's on <timeframe>"
    m = re.match(r"what'?s\s+on\s+(.+)", text, re.IGNORECASE)
    if m:
        return _ea_cli(["query", "--calendar", m.group(1).strip()])

    if first == "conflicts":
        return _ea_cli(["query", "--conflicts", rest or "this week"])

    # add: <description>
    if lower.startswith("add:"):
        description = text.split(":", 1)[1].strip()
        if not description:
            return CommandResult(ok=False, text="Usage: `add: <event description>`")
        return _ea_cli(["add-event", "--text", description])

    # Not a recognized command — let the caller decide (usually: ignore).
    return None


def _ea_cli(args: list[str]) -> CommandResult:
    """Invoke event-aggregator's CLI and format the output for Slack."""
    python = config.EVENT_AGGREGATOR_PYTHON
    main_py = config.EVENT_AGGREGATOR_DIR / "main.py"

    if not Path(python).exists() or not main_py.exists():
        return CommandResult(
            ok=False,
            text=f":warning: event-aggregator not installed at `{config.EVENT_AGGREGATOR_DIR}`",
        )

    try:
        result = subprocess.run(
            [python, str(main_py), *args],
            cwd=str(config.EVENT_AGGREGATOR_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(ok=False, text=f":hourglass: `{' '.join(args)}` timed out after 120s")

    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-10:])
        return CommandResult(
            ok=False,
            text=f":x: `{' '.join(args)}` failed (exit {result.returncode}):\n```\n{tail}\n```",
        )

    stdout = (result.stdout or "").strip()
    if not stdout:
        return CommandResult(ok=True, text=":white_check_mark: done")
    return CommandResult(ok=True, text=stdout)

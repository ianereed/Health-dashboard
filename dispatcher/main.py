"""
dispatcher CLI.

Usage:
  python main.py serve       # start Socket Mode listener (LaunchAgent runs this)
  python main.py check       # validate config + classifier + ea CLI wiring
"""
from __future__ import annotations

import sys
from pathlib import Path


def _cmd_serve() -> int:
    import slack_bot
    slack_bot.run()
    return 0


def _cmd_check() -> int:
    import subprocess

    import config

    ok = True
    problems = config.validate()
    if problems:
        ok = False
        for p in problems:
            print(f"  FAIL  {p}")
    else:
        print("  OK    config (tokens + paths)")

    # Spot-check event-aggregator's CLI: probe each subcommand's --help.
    # (main.py --help covers only legacy flags — subcommands are dispatched
    # inside __main__ before argparse runs, so each has its own argparse.)
    python = config.EVENT_AGGREGATOR_PYTHON
    main_py = config.EVENT_AGGREGATOR_DIR / "main.py"
    if Path(python).exists() and main_py.exists():
        for sub in ("classify", "ingest-image", "approve", "reject", "status", "query", "add-event"):
            try:
                result = subprocess.run(
                    [python, str(main_py), sub, "--help"],
                    cwd=str(config.EVENT_AGGREGATOR_DIR),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                present = result.returncode == 0 and "usage:" in (result.stdout + result.stderr)
                mark = "OK  " if present else "MISS"
                print(f"  {mark}  event-aggregator CLI subcommand: {sub}")
                if not present:
                    ok = False
            except Exception as exc:
                print(f"  FAIL  probe of {sub}: {exc}")
                ok = False
    else:
        print(f"  FAIL  event-aggregator python or main.py missing at {python}")
        ok = False

    print()
    print("READY" if ok else "NOT READY — fix the above before starting the LaunchAgent")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "serve":
        sys.exit(_cmd_serve())
    elif cmd == "check":
        sys.exit(_cmd_check())
    else:
        print(f"Unknown command: {cmd!r}")
        print(__doc__)
        sys.exit(1)

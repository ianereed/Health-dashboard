"""Tests for real preflight command: disk check, worker-loaded check."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from bake_off import cmd_preflight  # noqa: E402


def _make_args(
    ssh_host: str = "homeserver@homeserver",
    models_to_check: str = "qwen2.5vl:3b",
    out: str | None = None,
) -> argparse.Namespace:
    args = argparse.Namespace()
    args.ssh_host = ssh_host
    args.models_to_check = models_to_check
    args.out = out
    return args


_DF_PLENTY = (
    "Filesystem     Size   Used  Avail Capacity  Mounted on\n"
    "/dev/disk3s5  460Gi  100Gi  350Gi    22%    /System/Volumes/Data\n"
)
_DF_SCARCE = (
    "Filesystem     Size   Used  Avail Capacity  Mounted on\n"
    "/dev/disk3s5  460Gi  445Gi   10Gi    98%    /System/Volumes/Data\n"
)
_MEMORY_NORMAL = "The system memory pressure is currently at 10%: Normal\n"
_OLLAMA_LIST = "qwen2.5vl:3b  fb90415cde1e  3.2 GB  2 hours ago\n"


def test_preflight_bails_without_enough_disk(monkeypatch):
    """Mock df -h returning ~10GB available; assert preflight exits non-zero."""

    def mock_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        cmd_str = " ".join(str(c) for c in cmd)
        if "df" in cmd_str:
            result.stdout = _DF_SCARCE
        elif "launchctl" in cmd_str:
            # Worker not loaded
            result.returncode = 1
            result.stdout = ""
        elif "memory_pressure" in cmd_str:
            result.stdout = _MEMORY_NORMAL
        elif "ollama list" in cmd_str:
            result.stdout = _OLLAMA_LIST
        else:
            result.stdout = ""
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    rc = cmd_preflight(_make_args())
    assert rc != 0


def test_preflight_bails_when_workers_loaded(monkeypatch, capsys):
    """Mock launchctl print returning success; assert exit non-zero and 'bootout' in stderr."""

    def mock_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        cmd_str = " ".join(str(c) for c in cmd)
        if "df" in cmd_str:
            result.stdout = _DF_PLENTY
        elif "launchctl" in cmd_str:
            # Simulate both workers loaded
            result.returncode = 0
            result.stdout = "some launchctl output indicating service is running"
        elif "memory_pressure" in cmd_str:
            result.stdout = _MEMORY_NORMAL
        elif "ollama list" in cmd_str:
            result.stdout = _OLLAMA_LIST
        else:
            result.stdout = ""
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    rc = cmd_preflight(_make_args())

    assert rc != 0
    captured = capsys.readouterr()
    assert "bootout" in captured.err

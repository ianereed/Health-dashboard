"""CLI integration tests for bake_off.py (C1 scaffold)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BAKE_OFF = str(Path(__file__).parent.parent / "bake_off.py")


def _run(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, BAKE_OFF, *args],
        capture_output=True,
        text=True,
        **kwargs,
    )


def test_run_rejects_unknown_provider():
    result = _run("run", "--corpus", "/tmp", "--models", "foobar:1b")
    assert result.returncode != 0
    assert "unknown provider" in result.stderr


def test_run_accepts_known_providers(tmp_path):
    """Known providers pass the validation gate; fails later (corpus doesn't exist)
    but the error must NOT be an unknown-provider error."""
    corpus = tmp_path / "nonexistent"
    result = _run(
        "run",
        "--corpus", str(corpus),
        "--models", "qwen2.5vl:3b,gemini-2.5-flash",
        "--gemini-max-calls", "0",
    )
    assert result.returncode != 0
    assert "unknown provider" not in result.stderr

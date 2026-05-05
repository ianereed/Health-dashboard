"""Day 0 smoke test — gated behind RECIPE_BAKE_OFF_LIVE=1 to avoid CI hitting live Ollama.

Ollama on the mini is bound to localhost:11434 only. This test opens an SSH tunnel so
the laptop can reach it via http://localhost:11435 (port 11435 to avoid conflict with
any local Ollama instance).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

RECIPE_PHOTOS_DIR = Path(__file__).parent.parent / "recipe_photos"
BAKE_OFF = str(Path(__file__).parent.parent / "bake_off.py")
SSH_HOST = "homeserver@homeserver"
TUNNEL_LOCAL_PORT = 11435  # avoids collision with any local Ollama on 11434


@pytest.mark.skipif(
    not os.environ.get("RECIPE_BAKE_OFF_LIVE"),
    reason="Set RECIPE_BAKE_OFF_LIVE=1 to run live smoke test against mini Ollama",
)
def test_smoke_one_photo_qwen(tmp_path):
    """Smoke test: one real .JPG photo through qwen2.5vl:3b on the mini's Ollama.

    Establishes an SSH tunnel to mini's localhost:11434, runs the bake-off with
    --ollama-base-url pointing at the tunnel, then asserts 1 scored row with
    ingredient_f1 > 0.0.
    """
    photos = sorted(RECIPE_PHOTOS_DIR.glob("*.JPG")) + sorted(RECIPE_PHOTOS_DIR.glob("*.jpg"))
    assert photos, f"No .JPG/.jpg photos found in {RECIPE_PHOTOS_DIR}"

    photo = photos[0]

    # Open SSH tunnel: localhost:TUNNEL_LOCAL_PORT → mini's localhost:11434
    tunnel = subprocess.Popen(
        [
            "ssh", "-N", "-L",
            f"{TUNNEL_LOCAL_PORT}:localhost:11434",
            SSH_HOST,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)  # give tunnel time to establish

        result = subprocess.run(
            [
                sys.executable, BAKE_OFF,
                "run",
                "--corpus", str(RECIPE_PHOTOS_DIR),
                "--models", "qwen2.5vl:3b",
                "--corpus-glob", photo.name,
                "--ollama-base-url", f"http://localhost:{TUNNEL_LOCAL_PORT}",
                "--out", str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=5)

    if result.returncode != 0:
        pytest.fail(
            f"bake_off run failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    runs_path = tmp_path / "runs.jsonl"
    assert runs_path.exists(), "runs.jsonl was not written"

    rows = [json.loads(line) for line in runs_path.read_text().splitlines() if line.strip()]
    scored_rows = [r for r in rows if r.get("status") == "scored"]

    assert len(scored_rows) == 1, (
        f"Expected 1 scored row, got {len(scored_rows)}. "
        f"All statuses: {[r['status'] for r in rows]}\n"
        f"stderr: {result.stderr}"
    )

    f1 = scored_rows[0]["score"]["ingredient_f1"]
    print(f"\nSmoke: model=qwen2.5vl:3b photo={photo.name} ingredient_f1={f1:.3f}", flush=True)
    assert f1 > 0.0, f"Expected ingredient_f1 > 0.0, got {f1}"

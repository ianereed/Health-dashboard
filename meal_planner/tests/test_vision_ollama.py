"""T2 — verify that a network error (requests.Timeout) does not trigger a retry.

Before the fix, _ollama.py:200 had:
    if md1.get("http_status") and md1["http_status"] != 200:
When http_status is None (RequestException path), None and ... is falsy, so
the check was skipped and validate_schema(None) ran, causing a retry.
After the fix:
    if md1.get("http_status") != 200:
None != 200 is True, so the function returns immediately without retry.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
import requests


def _fake_image(tmp_path: Path) -> Path:
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
    return p


def test_timeout_does_not_trigger_retry(tmp_path, monkeypatch):
    """requests.Timeout on the first call → n_retries == 0, no second call."""
    call_count = 0

    def _fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.Timeout("timed out")

    monkeypatch.setattr("requests.post", _fake_post)

    from meal_planner.vision._ollama import call_ollama_vision

    photo = _fake_image(tmp_path)
    parsed, metadata = call_ollama_vision(
        "llama3.2-vision:11b", photo, "Extract recipe.",
        timeout_s=1,
    )

    assert parsed is None
    assert metadata["n_retries"] == 0
    assert call_count == 1, f"Expected 1 call (no retry), got {call_count}"

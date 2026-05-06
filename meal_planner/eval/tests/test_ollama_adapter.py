"""Tests for _call_ollama_vision: mocked HTTP, JSON parse failure, 429 handling."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import requests  # noqa: E402 (needed before bake_off import for monkeypatch)
from bake_off import _call_ollama_vision  # noqa: E402


def test_call_ollama_vision_mocked(monkeypatch, tmp_path):
    """Mock requests.post to return canned Ollama JSON; assert parsed dict + metadata."""
    photo = tmp_path / "recipe.jpg"
    photo.write_bytes(b"\xff\xd8\xff")

    canned = {
        "title": "Test Recipe",
        "ingredients": [{"qty": "1", "unit": "cup", "name": "flour"}],
        "tags": ["baking"],
    }
    ollama_body = {
        "model": "qwen2.5vl:3b",
        "response": json.dumps(canned),
        "eval_count": 42,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = json.dumps(ollama_body)
    mock_resp.json.return_value = ollama_body

    monkeypatch.setattr(requests, "post", lambda *a, **kw: mock_resp)

    parsed, metadata = _call_ollama_vision("qwen2.5vl:3b", photo, "extract this recipe")

    assert parsed is not None
    assert parsed["title"] == "Test Recipe"
    assert len(parsed["ingredients"]) == 1
    assert metadata["eval_count"] == 42
    assert metadata["latency_s"] is not None
    assert metadata["latency_s"] >= 0


def test_call_ollama_handles_invalid_json(monkeypatch, tmp_path):
    """Mock returns non-JSON in response field; assert (None, metadata) with raw captured."""
    photo = tmp_path / "recipe.jpg"
    photo.write_bytes(b"\xff\xd8\xff")

    ollama_body = {
        "model": "qwen2.5vl:3b",
        "response": "Sorry, I cannot extract this recipe.",
        "eval_count": 10,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = json.dumps(ollama_body)
    mock_resp.json.return_value = ollama_body

    monkeypatch.setattr(requests, "post", lambda *a, **kw: mock_resp)

    parsed, metadata = _call_ollama_vision("qwen2.5vl:3b", photo, "extract this recipe")

    assert parsed is None
    assert metadata["raw_response"] is not None
    assert "Sorry" in metadata["raw_response"]


def test_retry_on_schema_fail_recovers(monkeypatch, tmp_path):
    """First response is missing the 'name' key on an ingredient; retry returns valid JSON.

    Asserts the function makes 2 calls, returns the valid retry result, and records
    n_retries=1 + retry_latency_s in metadata.
    """
    photo = tmp_path / "recipe.jpg"
    photo.write_bytes(b"\xff\xd8\xff")

    bad = {
        "title": "Test Recipe",
        "ingredients": [{"qty": "1", "unit": "cup"}],  # missing 'name' key
        "tags": [],
    }
    good = {
        "title": "Test Recipe",
        "ingredients": [{"qty": "1", "unit": "cup", "name": "flour"}],
        "tags": ["baking"],
    }

    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        body = bad if call_count == 1 else good
        ollama_body = {"model": "qwen2.5vl:3b", "response": json.dumps(body), "eval_count": 11}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(ollama_body)
        mock_resp.json.return_value = ollama_body
        return mock_resp

    monkeypatch.setattr(requests, "post", mock_post)

    parsed, metadata = _call_ollama_vision("qwen2.5vl:3b", photo, "extract this recipe")

    assert call_count == 2, "must retry once on schema fail"
    assert parsed is not None
    assert parsed["ingredients"][0]["name"] == "flour"
    assert metadata["n_retries"] == 1
    assert metadata["retry_latency_s"] is not None and metadata["retry_latency_s"] >= 0


def test_no_retry_on_first_call_valid(monkeypatch, tmp_path):
    """First response is valid → no retry, n_retries stays 0."""
    photo = tmp_path / "recipe.jpg"
    photo.write_bytes(b"\xff\xd8\xff")

    good = {
        "title": "T",
        "ingredients": [{"qty": "1", "unit": "cup", "name": "flour"}],
        "tags": [],
    }
    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        ollama_body = {"model": "qwen2.5vl:3b", "response": json.dumps(good), "eval_count": 5}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(ollama_body)
        mock_resp.json.return_value = ollama_body
        return mock_resp

    monkeypatch.setattr(requests, "post", mock_post)

    _, metadata = _call_ollama_vision("qwen2.5vl:3b", photo, "extract this recipe")
    assert call_count == 1
    assert metadata["n_retries"] == 0
    assert metadata["retry_latency_s"] is None


def test_429_no_retry(monkeypatch, tmp_path):
    """429 must not be retried and must not produce a parsed result.

    Regression gate for 2026-05-04 incident: Ollama returned HTTP 429 with
    empty body; downstream json.loads("") raised silently and produced {}.
    The fix is to short-circuit on non-200 status before any JSON parsing.
    """
    photo = tmp_path / "recipe.jpg"
    photo.write_bytes(b"\xff\xd8\xff")

    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = ""
        return mock_resp

    monkeypatch.setattr(requests, "post", mock_post)

    parsed, metadata = _call_ollama_vision("qwen2.5vl:3b", photo, "extract this recipe")

    assert call_count == 1, "must not retry on 429"
    assert parsed is None, "429 must not produce a parsed result"
    assert "429" in (metadata.get("raw_response") or ""), "metadata must record the HTTP 429"

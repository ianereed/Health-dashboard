"""
Tests for per-call keep_alive_override in _ModelState.

Covers:
  - keep_alive_override propagates from ensure() → swap_to() → warmup POST body
  - Default keep_alive unchanged when no override given
  - @requires_model(keep_alive=N) decorator forwards the override
  - record_swap() writes to_kind field to model_swaps.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobs.lib import _model_state, record_swap, requires_model


@pytest.fixture(autouse=True)
def reset_model_state():
    """Each test starts with a clean singleton."""
    _model_state._current = None
    _model_state._batch_kinds = set()
    yield
    _model_state._current = None
    _model_state._batch_kinds = set()


@pytest.fixture
def capture_posts(monkeypatch):
    """Capture all _http_post calls; return the list."""
    calls: list[dict] = []

    def _fake(url: str, payload: dict, timeout: int = 120) -> None:
        calls.append({"url": url, "payload": payload})

    monkeypatch.setattr(_model_state, "_http_post", _fake)
    return calls


def test_keep_alive_override_propagates_to_swap_to(capture_posts, monkeypatch):
    """ensure('vision', keep_alive_override=300) must send keep_alive=300 in warmup POST."""
    monkeypatch.setenv("LOCAL_VISION_MODEL", "llama3.2-vision:11b")

    with _model_state._lock:
        _model_state.ensure("vision", keep_alive_override=300)

    warmups = [c for c in capture_posts if c["payload"].get("keep_alive") != 0]
    assert len(warmups) == 1, f"expected 1 warmup POST, got {len(warmups)}"
    assert warmups[0]["payload"]["keep_alive"] == 300, (
        f"expected keep_alive=300, got {warmups[0]['payload'].get('keep_alive')!r}"
    )


def test_default_keep_alive_unchanged(capture_posts, monkeypatch):
    """ensure('vision') with no override must use OLLAMA_KEEP_ALIVE_VISION default."""
    monkeypatch.setenv("LOCAL_VISION_MODEL", "llama3.2-vision:11b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE_VISION", "30s")

    with _model_state._lock:
        _model_state.ensure("vision")

    warmups = [c for c in capture_posts if c["payload"].get("keep_alive") != 0]
    assert len(warmups) == 1, f"expected 1 warmup POST, got {len(warmups)}"
    assert warmups[0]["payload"]["keep_alive"] == "30s", (
        f"expected keep_alive='30s' (parsed default), got {warmups[0]['payload'].get('keep_alive')!r}"
    )


def test_decorator_forwards_keep_alive(capture_posts, monkeypatch):
    """@requires_model('vision', keep_alive=300) must send keep_alive=300 in warmup POST."""
    monkeypatch.setenv("LOCAL_VISION_MODEL", "llama3.2-vision:11b")

    @requires_model("vision", keep_alive=300)
    def do_vision():
        return "ok"

    result = do_vision()
    assert result == "ok"

    warmups = [c for c in capture_posts if c["payload"].get("keep_alive") == 300]
    assert len(warmups) == 1, (
        f"expected 1 warmup POST with keep_alive=300, got {len(warmups)} "
        f"(all calls: {[c['payload'].get('keep_alive') for c in capture_posts]})"
    )


def test_record_swap_writes_to_kind(tmp_path, monkeypatch):
    """record_swap() must write to_kind field when kind is provided."""
    log_path = tmp_path / "model_swaps.jsonl"
    import jobs.lib as _lib
    monkeypatch.setattr(_lib, "_MODEL_SWAP_LOG", log_path)

    record_swap("qwen3:14b", "llama3.2-vision:11b", latency_ms=1500, kind="vision")

    assert log_path.exists()
    row = json.loads(log_path.read_text().strip())
    assert row["to"] == "llama3.2-vision:11b"
    assert row["to_kind"] == "vision", f"expected to_kind='vision', got {row.get('to_kind')!r}"
    assert row["latency_ms"] == 1500
    assert "ts" in row


def test_record_swap_without_kind_omits_to_kind(tmp_path, monkeypatch):
    """record_swap() must not write to_kind when kind is not provided (backward compat)."""
    log_path = tmp_path / "model_swaps.jsonl"
    import jobs.lib as _lib
    monkeypatch.setattr(_lib, "_MODEL_SWAP_LOG", log_path)

    record_swap("none", "qwen3:14b", latency_ms=2000)

    row = json.loads(log_path.read_text().strip())
    assert "to_kind" not in row, f"to_kind should be absent when not provided, got {row}"

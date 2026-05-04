"""
Phase 12.6 — @requires_model primitive unit tests.

Covers: no-swap on same-kind repeat, swap on opposite-kind, batch_hint
suppresses mid-batch opposite-kind swap, record_swap writes JSONL.
All Ollama HTTP calls are intercepted via monkeypatching _model_state._http_post.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobs.lib import _model_state, record_swap, requires_model


@pytest.fixture(autouse=True)
def reset_model_state():
    """Each test starts with a clean singleton: no model loaded, no batch."""
    _model_state._current = None
    _model_state._batch_kinds = set()
    yield
    _model_state._current = None
    _model_state._batch_kinds = set()


@pytest.fixture
def capture_posts(monkeypatch):
    """Capture payloads sent to Ollama; return the list for inspection."""
    calls: list[dict] = []

    def _fake_post(url: str, payload: dict, timeout: int = 120) -> None:
        calls.append({"url": url, "payload": payload})

    monkeypatch.setattr(_model_state, "_http_post", _fake_post)
    return calls


def test_no_swap_same_model_twice(capture_posts, monkeypatch):
    """Second call to requires_model("text") must not issue another Ollama request."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")

    @requires_model("text")
    def do_text():
        return "ok"

    do_text()
    calls_after_first = len(capture_posts)
    do_text()
    assert len(capture_posts) == calls_after_first, (
        "second same-kind call should not POST to Ollama"
    )


def test_swap_triggered_on_opposite_kind(capture_posts, monkeypatch):
    """Calling text then vision must unload text and warmup vision."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    monkeypatch.setenv("LOCAL_VISION_MODEL", "qwen2.5vl:7b")

    @requires_model("text")
    def do_text():
        return "text"

    @requires_model("vision")
    def do_vision():
        return "vision"

    do_text()
    initial_count = len(capture_posts)
    do_vision()

    # Must have posted: unload text (keep_alive=0) + warmup vision
    new_calls = capture_posts[initial_count:]
    assert len(new_calls) == 2
    unload_payload = new_calls[0]["payload"]
    warmup_payload = new_calls[1]["payload"]
    assert unload_payload["model"] == "qwen3:14b"
    assert unload_payload["keep_alive"] == 0
    assert warmup_payload["model"] == "qwen2.5vl:7b"
    assert warmup_payload.get("keep_alive") != 0


def test_batch_hint_suppresses_opposite_kind_mid_batch(capture_posts, monkeypatch):
    """@requires_model("text", batch_hint="drain") must block vision swaps mid-call."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    monkeypatch.setenv("LOCAL_VISION_MODEL", "qwen2.5vl:7b")

    inner_ran = {"called": False}

    @requires_model("vision")
    def do_vision_inner():
        inner_ran["called"] = True

    @requires_model("text", batch_hint="drain")
    def do_text_with_inner_vision():
        # While text batch is active, this vision call must be deferred (no-op).
        do_vision_inner()
        return "done"

    do_text_with_inner_vision()
    # The inner vision call ran, but should NOT have caused a model swap.
    assert inner_ran["called"]
    # Only the initial text warmup should have fired (1 POST for warmup, no unload
    # since _current was None). No vision warmup.
    vision_warmups = [
        c for c in capture_posts if c["payload"].get("model") == "qwen2.5vl:7b"
    ]
    assert not vision_warmups, "vision warmup must be deferred while text batch is active"


def test_batch_hint_clears_after_return(capture_posts, monkeypatch):
    """After the batch_hint="drain" function returns, _batch_kinds must be empty."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")

    @requires_model("text", batch_hint="drain")
    def do_text():
        return "ok"

    do_text()
    assert len(_model_state._batch_kinds) == 0


def test_record_swap_writes_jsonl(tmp_path, monkeypatch):
    """record_swap appends a valid JSON row to model_swaps.jsonl."""
    log_path = tmp_path / "model_swaps.jsonl"
    import jobs.lib as _lib
    monkeypatch.setattr(_lib, "_MODEL_SWAP_LOG", log_path)

    record_swap("qwen3:14b", "qwen2.5vl:7b", latency_ms=4200)

    assert log_path.exists()
    row = json.loads(log_path.read_text().strip())
    assert row["from"] == "qwen3:14b"
    assert row["to"] == "qwen2.5vl:7b"
    assert row["latency_ms"] == 4200
    assert "ts" in row


# ── Fix 16: warmup-fail and unload-fail tests ─────────────────────────────────


def test_warmup_failure_leaves_current_as_none(monkeypatch):
    """When warmup HTTP raises, _current must be set to None (not the target model)."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    call_count = [0]

    def _failing_post(url, payload, timeout=120):
        call_count[0] += 1
        # Allow the unload call but fail on warmup (keep_alive != 0 means warmup).
        if payload.get("keep_alive") != 0 and payload.get("keep_alive") is not None:
            raise ConnectionError("Ollama is down")

    monkeypatch.setattr(_model_state, "_http_post", _failing_post)

    @requires_model("text")
    def do_text():
        return "ran"

    do_text()
    assert _model_state._current is None, (
        "_current must be None after warmup failure, not the target model"
    )


def test_warmup_success_sets_current(monkeypatch):
    """When warmup succeeds, _current must be set to the target model name."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    monkeypatch.setattr(_model_state, "_http_post", lambda *a, **kw: None)

    @requires_model("text")
    def do_text():
        return "ran"

    do_text()
    assert _model_state._current == "qwen3:14b"


def test_unload_failure_does_not_block_swap(monkeypatch):
    """Unload failure (best-effort) must not prevent the new model from being attempted."""
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    monkeypatch.setenv("LOCAL_VISION_MODEL", "qwen2.5vl:7b")

    warmup_calls = []

    def _selective_post(url, payload, timeout=120):
        if payload.get("keep_alive") == 0:
            raise ConnectionError("unload failed")
        warmup_calls.append(payload.get("model"))

    monkeypatch.setattr(_model_state, "_http_post", _selective_post)

    @requires_model("text")
    def do_text():
        return "text"

    @requires_model("vision")
    def do_vision():
        return "vision"

    do_text()
    # Text warmup should have succeeded.
    assert "qwen3:14b" in warmup_calls

    do_vision()
    # Vision warmup should have been attempted even though unload failed.
    assert "qwen2.5vl:7b" in warmup_calls

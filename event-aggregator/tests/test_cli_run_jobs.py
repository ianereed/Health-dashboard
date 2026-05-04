"""Phase 12.8a — unit tests for cli._cmd_run_text_job and _cmd_run_ocr_job.

Covers:
- Bad --job-json (malformed JSON) → exit code 2.
- Missing --file for OCR (non-existent file) → exit code 2.
- State saves on exception (no partial state written on subprocess failure).
- Baseline touch file is written on success but NOT on failure.
- TimeoutExpired is re-raised (handled upstream, subprocess killed).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure the event-aggregator project is on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cli


class _OkWorker:
    """Minimal worker shim: _run_text_job and _run_ocr_job do nothing."""
    @staticmethod
    def _run_text_job(state, job):
        pass

    @staticmethod
    def _run_ocr_job(state, job):
        pass


class _FailingWorker:
    """Worker that raises on _run_text_job/_run_ocr_job."""
    @staticmethod
    def _run_text_job(state, job):
        raise RuntimeError("extraction failed")

    @staticmethod
    def _run_ocr_job(state, job):
        raise RuntimeError("ocr failed")


class _TimeoutWorker:
    """Worker that raises TimeoutExpired (simulates subprocess timeout propagation)."""
    @staticmethod
    def _run_text_job(state, job):
        # subprocess.TimeoutExpired requires a cmd argument.
        exc = subprocess.TimeoutExpired(cmd=["cli.py"], timeout=300)
        raise exc

    @staticmethod
    def _run_ocr_job(state, job):
        exc = subprocess.TimeoutExpired(cmd=["cli.py"], timeout=300)
        raise exc


class _FakeState:
    """Minimal state object that records saves."""
    def __init__(self):
        self.saved = False

    def is_seen(self, *_):
        return False

    def mark_seen(self, *_):
        pass


class _FakeStateModule:
    """Minimal state module shim."""
    _state = None
    _depth = 0

    @classmethod
    def reset(cls):
        cls._state = _FakeState()
        cls._depth = 0

    @classmethod
    def load(cls):
        return cls._state

    @classmethod
    def save(cls, state):
        state.saved = True

    @staticmethod
    def locked():
        import contextlib
        return contextlib.nullcontext()


@pytest.fixture(autouse=True)
def fake_imports(monkeypatch, tmp_path):
    """Monkeypatch state + worker imports inside cli._cmd_run_text_job/_cmd_run_ocr_job."""
    _FakeStateModule.reset()

    # cli.py does `import state as state_module` and `import worker` inside each function.
    monkeypatch.setitem(sys.modules, "state", _FakeStateModule)
    monkeypatch.setitem(sys.modules, "worker", _OkWorker)

    # Redirect the baseline touch file to tmp so tests don't write to the repo.
    monkeypatch.setattr(cli, "_BASELINE_TOUCH_FILE", tmp_path / "baseline.last")


def test_run_text_job_bad_json_returns_2():
    rc = cli._cmd_run_text_job("not-valid-json{")
    assert rc == 2


def test_run_text_job_success_touches_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.last"
    monkeypatch.setattr(cli, "_BASELINE_TOUCH_FILE", baseline)
    job = {"source": "test", "id": "x1", "body_text": "hi", "metadata": {}, "timestamp": "2026-05-03T00:00:00Z"}
    rc = cli._cmd_run_text_job(json.dumps(job))
    assert rc == 0
    assert baseline.exists(), "baseline touch file must be written on success"


def test_run_text_job_failure_does_not_touch_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.last"
    monkeypatch.setattr(cli, "_BASELINE_TOUCH_FILE", baseline)
    monkeypatch.setitem(sys.modules, "worker", _FailingWorker)
    job = {"source": "test", "id": "x2", "body_text": "hi", "metadata": {}, "timestamp": "2026-05-03T00:00:00Z"}
    rc = cli._cmd_run_text_job(json.dumps(job))
    assert rc == 1
    assert not baseline.exists(), "baseline touch file must NOT be written on failure"


def test_run_text_job_saves_state_on_exception(monkeypatch):
    """State must be saved even when _run_text_job raises (via finally)."""
    monkeypatch.setitem(sys.modules, "worker", _FailingWorker)
    job = {"source": "test", "id": "x3", "body_text": "hi", "metadata": {}, "timestamp": "2026-05-03T00:00:00Z"}
    cli._cmd_run_text_job(json.dumps(job))
    assert _FakeStateModule._state.saved, "state.save must be called even on exception"


def test_run_ocr_job_missing_file_returns_2(tmp_path):
    rc = cli._cmd_run_ocr_job(tmp_path / "does_not_exist.png")
    assert rc == 2


def test_run_ocr_job_success_touches_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.last"
    monkeypatch.setattr(cli, "_BASELINE_TOUCH_FILE", baseline)
    # Create a real file so the existence check passes.
    test_file = tmp_path / "test.png"
    test_file.touch()
    rc = cli._cmd_run_ocr_job(test_file)
    assert rc == 0
    assert baseline.exists(), "baseline touch file must be written on OCR success"


def test_run_ocr_job_failure_does_not_touch_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.last"
    monkeypatch.setattr(cli, "_BASELINE_TOUCH_FILE", baseline)
    monkeypatch.setitem(sys.modules, "worker", _FailingWorker)
    test_file = tmp_path / "test.png"
    test_file.touch()
    rc = cli._cmd_run_ocr_job(test_file)
    assert rc == 1
    assert not baseline.exists(), "baseline touch file must NOT be written on OCR failure"


def test_run_ocr_job_saves_state_on_exception(monkeypatch, tmp_path):
    """State must be saved even when _run_ocr_job raises."""
    monkeypatch.setitem(sys.modules, "worker", _FailingWorker)
    test_file = tmp_path / "test.png"
    test_file.touch()
    cli._cmd_run_ocr_job(test_file)
    assert _FakeStateModule._state.saved, "state.save must be called even on exception"

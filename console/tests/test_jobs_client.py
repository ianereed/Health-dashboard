"""Unit tests for console/jobs_client.py.

All HTTP calls are mocked via unittest.mock.patch so no real server is
needed. Tests cover the happy path, error paths, and the hard invariant
that no console/ file imports from the `jobs` package directly.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(body: dict, status: int = 200) -> MagicMock:
    """Build a mock for what urllib.request.urlopen().__enter__() returns."""
    encoded = json.dumps(body).encode()
    resp = MagicMock()
    resp.read.return_value = encoded
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _import_client():
    from console import jobs_client
    return jobs_client


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------

def test_enqueue_success(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    resp = _make_response({"id": "abc-123", "kind": "nop"})
    with patch("urllib.request.urlopen", return_value=resp):
        task_id = client.enqueue("nop", {"echo": {"hi": 1}})
    assert task_id == "abc-123"


def test_enqueue_5xx_raises(monkeypatch):
    import urllib.error
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    err = urllib.error.HTTPError(
        url="http://localhost:8504/jobs",
        code=500,
        msg="Internal Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps({"error": "boom"}).encode()),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        try:
            client.enqueue("nop")
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "boom" in str(exc)


# ---------------------------------------------------------------------------
# queue_size
# ---------------------------------------------------------------------------

def test_queue_size_200(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    resp = _make_response({"size": 7})
    with patch("urllib.request.urlopen", return_value=resp):
        size = client.queue_size()
    assert size == 7


def test_queue_size_network_error_returns_none(monkeypatch):
    import urllib.error
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        size = client.queue_size()
    assert size is None


# ---------------------------------------------------------------------------
# result
# ---------------------------------------------------------------------------

def test_result_pending_returns_none(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    resp = _make_response({"status": "pending", "result": None, "error": None})
    with patch("urllib.request.urlopen", return_value=resp):
        out = client.result("some-id")
    assert out is None


def test_result_terminal_success_returns_dict(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    payload = {"items_sent": 3, "items_attempted": 3, "error": None}
    resp = _make_response({"status": "success", "result": payload, "error": None})
    with patch("urllib.request.urlopen", return_value=resp):
        out = client.result("some-id")
    assert out == payload


def test_result_error_status_returns_synthesized_dict(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    resp = _make_response({
        "status": "error",
        "result": None,
        "error": "task crashed: IndexError: list index out of range",
    })
    with patch("urllib.request.urlopen", return_value=resp):
        out = client.result("some-id")
    assert isinstance(out, dict)
    assert "IndexError" in out["error"]
    assert out["items_sent"] == 0
    assert out["items_attempted"] == 0


def test_result_network_error_returns_synthesized_dict(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        out = client.result("some-id")
    assert isinstance(out, dict)
    assert "poll failed" in out["error"]
    assert "OSError" in out["error"]
    assert out["items_sent"] == 0


# ---------------------------------------------------------------------------
# kinds
# ---------------------------------------------------------------------------

def test_kinds_success(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    kind_list = [{"name": "nop", "baseline": None, "requires": []}]
    resp = _make_response({"kinds": kind_list})
    with patch("urllib.request.urlopen", return_value=resp):
        out = client.kinds()
    assert out == kind_list


def test_kinds_network_error_returns_empty(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        out = client.kinds()
    assert out == []


def test_enqueue_missing_id_raises(monkeypatch):
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    resp = _make_response({"kind": "nop"})  # no "id" field
    with patch("urllib.request.urlopen", return_value=resp):
        try:
            client.enqueue("nop")
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "no id in response" in str(exc)


# ---------------------------------------------------------------------------
# Hard invariant: no console/ file imports from the jobs package
# ---------------------------------------------------------------------------

def test_no_jobs_import_in_console():
    """grep -rE 'from jobs($|\\.|[[:space:]])' console/ must return 0 lines.

    This ensures no streamlit process opens the huey SQLite WAL fd by
    importing the jobs package (or any of its subpackages) directly.
    """
    repo_root = Path(__file__).resolve().parents[2]
    console_dir = repo_root / "console"
    result = subprocess.run(
        [
            "grep", "-rE",
            "--exclude-dir=tests",
            r"from jobs($|\.|[[:space:]])",
            str(console_dir),
        ],
        capture_output=True,
        text=True,
    )
    matches = result.stdout.strip()
    assert matches == "", "console/ source still imports from jobs package:\n" + matches

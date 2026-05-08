"""Unit tests for console/jobs_client.py.

All HTTP calls are mocked via unittest.mock.patch so no real server is
needed. Tests cover the happy path, error paths, and the hard invariant
that no console/ file imports from the `jobs` package directly.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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
        with pytest.raises(RuntimeError, match="boom"):
            client.enqueue("nop")


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
    # Pin the response-size cap so a future refactor can't silently drop it.
    resp.read.assert_called_with(client._MAX_RESPONSE_BYTES)


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


def test_result_network_error_returns_none(monkeypatch):
    """Transient network errors must NOT fail the job in the UI — return None
    so the fragment treats it as pending and retries on the next 2s tick.
    The job is still running on the worker; only the poll failed."""
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        out = client.result("some-id")
    assert out is None


def test_result_http_error_returns_synthesized_dict(monkeypatch):
    """Server-reported HTTP errors (4xx/5xx) DO surface as terminal — the
    server reached us and said something concrete went wrong."""
    import urllib.error
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    err = urllib.error.HTTPError(
        url="http://localhost:8504/jobs/some-id",
        code=500,
        msg="Internal Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps({"error": "task crashed: KeyError"}).encode()),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        out = client.result("some-id")
    assert isinstance(out, dict)
    assert "task crashed" in out["error"]
    assert out["items_sent"] == 0
    assert out["items_attempted"] == 0


def test_result_http_error_with_unparseable_body_falls_back(monkeypatch):
    """If the HTTPError body isn't JSON, fall back to the status code."""
    import urllib.error
    monkeypatch.setenv("HOME_TOOLS_HTTP_TOKEN", "tok")
    monkeypatch.setenv("HOME_TOOLS_HTTP_URL", "http://localhost:8504")
    client = _import_client()
    err = urllib.error.HTTPError(
        url="http://localhost:8504/jobs/some-id",
        code=502,
        msg="Bad Gateway",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b"<html>nginx</html>"),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        out = client.result("some-id")
    assert isinstance(out, dict)
    assert "HTTP 502" in out["error"]


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
        with pytest.raises(RuntimeError, match="no id in response"):
            client.enqueue("nop")


# ---------------------------------------------------------------------------
# Hard invariant: no console/ file imports from the jobs package
# ---------------------------------------------------------------------------

def test_no_jobs_import_in_console():
    """No console source file may import the jobs package by any path.

    Catches `from jobs[...]`, `import jobs[...]` (anchored to start-of-line so
    `efrom jobs` etc. don't false-positive), and dynamic imports via
    `__import__("jobs...")` or `importlib.import_module("jobs...")`. Any of
    these would re-open the SQLite WAL fd because jobs/__init__.py auto-imports
    submodules that construct SqliteHuey() at module-import time.
    """
    repo_root = Path(__file__).resolve().parents[2]
    console_dir = repo_root / "console"
    static_grep = subprocess.run(
        [
            "grep", "-rEn",
            "--exclude-dir=tests",
            r"^[[:space:]]*(from|import)[[:space:]]+jobs($|\.|[[:space:]])",
            str(console_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert static_grep.stdout.strip() == "", (
        "console/ source still imports from jobs package:\n" + static_grep.stdout
    )

    dynamic_grep = subprocess.run(
        [
            "grep", "-rEn",
            "--exclude-dir=tests",
            r"""(__import__\(['"]jobs(['"]|\.)|importlib[^(]*\(['"]jobs(['"]|\.))""",
            str(console_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert dynamic_grep.stdout.strip() == "", (
        "console/ source uses dynamic jobs import:\n" + dynamic_grep.stdout
    )

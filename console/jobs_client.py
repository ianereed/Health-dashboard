"""HTTP client for the jobs service (enqueue_http, :8504).

Encapsulates all network access so the console process never opens the
huey SQLite WAL fd — every operation routes through the HTTP API instead
of importing the jobs package.

Env:
  HOME_TOOLS_HTTP_TOKEN  bearer token (required for authenticated calls)
  HOME_TOOLS_HTTP_URL    base URL (default http://100.66.241.126:8504)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_DEFAULT_BASE_URL = "http://100.66.241.126:8504"
_MAX_RESPONSE_BYTES = 1_048_576  # 1 MB — guard against runaway server responses


def base_url() -> str:
    return os.environ.get("HOME_TOOLS_HTTP_URL", _DEFAULT_BASE_URL).rstrip("/")


def _token() -> str:
    return os.environ.get("HOME_TOOLS_HTTP_TOKEN", "")


def _do_request(method: str, path: str, body: dict | None = None) -> dict:
    url = base_url() + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read(_MAX_RESPONSE_BYTES))


def enqueue(kind: str, params: dict | None = None) -> str:
    """Enqueue a job. Returns the task_id string. Raises RuntimeError on failure."""
    try:
        resp = _do_request("POST", "/jobs", {"kind": kind, "params": params or {}})
    except urllib.error.HTTPError as exc:
        err_body = exc.read()
        try:
            detail = json.loads(err_body).get("error", err_body.decode(errors="replace"))
        except Exception:
            detail = err_body.decode(errors="replace")
        raise RuntimeError(f"enqueue {kind!r} failed ({exc.code}): {detail}") from exc
    task_id = resp.get("id")
    if task_id is None:
        raise RuntimeError(f"enqueue {kind!r}: no id in response: {resp}")
    return task_id


def queue_size() -> int | None:
    """Return the current queue depth, or None on any error."""
    try:
        resp = _do_request("GET", "/queue-size")
        return resp.get("size")
    except Exception:
        return None


def kinds() -> list[dict]:
    """Return the list of registered job kinds from GET /kinds. Empty list on error."""
    try:
        resp = _do_request("GET", "/kinds")
        return resp.get("kinds", [])
    except Exception:
        return []


def result(task_id: str) -> dict | None:
    """Poll for a task result.

    Returns:
      None — task is still pending
      dict — terminal: either the kind's own result-dict (status=success)
             or a synthesized error dict shaped for _format_status (status=error)
    """
    try:
        resp = _do_request("GET", f"/jobs/{task_id}")
    except Exception as exc:
        return {
            "error": f"poll failed: {type(exc).__name__}: {exc}",
            "items_sent": 0,
            "items_attempted": 0,
        }
    status = resp.get("status", "error")
    if status == "pending":
        return None
    if status == "success":
        payload = resp.get("result") or {}
        return payload if isinstance(payload, dict) else {"result": payload}
    return {
        "error": resp.get("error") or f"unexpected status {status!r}",
        "items_sent": 0,
        "items_attempted": 0,
    }

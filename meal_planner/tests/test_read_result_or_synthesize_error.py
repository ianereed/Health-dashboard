"""Integration tests for _read_result_or_synthesize_error.

These tests exercise the actual read path (the helper that wraps a
result_fn callable), which the pure-format tests in
test_render_job_status_pure.py cannot — they feed dicts directly into
_format_status and bypass the result_fn entirely.

The third test (taskexception_synthesizes_error_dict) is the regression
guard for the result_fn safety net: any exception raised by the result_fn
(formerly a raw huey.result() call) is caught and synthesized into an
error dict, so a crashing poll never exception-loops a @st.fragment.
"""
from __future__ import annotations


def _read():
    from console.tabs._job_status import _read_result_or_synthesize_error
    return _read_result_or_synthesize_error


def _fmt():
    from console.tabs._job_status import _format_status
    return _format_status


def test_read_result_pending_returns_none() -> None:
    result_fn = lambda task_id: None
    out = _read()(result_fn, "task-id-pending")
    assert out is None


def test_read_result_success_returns_dict_unchanged() -> None:
    payload = {
        "items_sent": 3,
        "items_attempted": 3,
        "consolidate_failed": None,
        "consolidate_dropped": 0,
        "error": None,
    }
    result_fn = lambda task_id: payload
    out = _read()(result_fn, "task-id-success")
    assert out == payload
    level, _ = _fmt()(out)
    assert level == "success"


def test_read_result_taskexception_synthesizes_error_dict() -> None:
    """Regression guard: pre-fix, this raised straight through the
    fragment and the user never saw a red banner. The helper must catch,
    synthesize, and let _format_status return ('error', ...) so the
    fragment renders red and clears session_state."""
    try:
        from huey.exceptions import TaskException

        exc: Exception = TaskException({"error": "KeyError(99999999)"})
    except Exception:
        # If huey is not importable, any Exception stands in;
        # the helper catches Exception, not just TaskException.
        exc = RuntimeError("KeyError(99999999)")

    def _raise(task_id):
        raise exc

    out = _read()(_raise, "task-id-failed")
    assert isinstance(out, dict)
    assert out["error"]
    assert "task crashed" in out["error"]
    assert out["items_sent"] == 0
    assert out["items_attempted"] == 0
    level, msg = _fmt()(out)
    assert level == "error"
    assert "failed" in msg.lower()


def test_read_result_generic_exception_also_caught() -> None:
    """DB-lock or import-time failures in the future should also surface
    as a red banner, not crash the tab. The helper catches Exception, so
    any subclass works."""

    def _raise(task_id):
        raise OSError("disk full")

    out = _read()(_raise, "task-id-disk-full")
    assert isinstance(out, dict)
    assert "OSError" in out["error"]
    assert "disk full" in out["error"]
    level, _ = _fmt()(out)
    assert level == "error"

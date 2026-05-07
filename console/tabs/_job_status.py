"""Pure helpers for the job-status fragment.

Lives in its own module (no pandas / streamlit imports at top level) so the
helpers are importable from `jobs/.venv` for failure-path spikes on the mini.
"""
from __future__ import annotations


def _format_status(result: object) -> tuple[str, str]:
    """Map a kind result dict to (level, message).

    level is one of "success", "warning", "error".
    """
    if not isinstance(result, dict):
        return ("error", f"unexpected result shape: {result!r}")
    err = result.get("error") or result.get("consolidate_failed")
    sent = result.get("items_sent", result.get("items_cleared", 0))
    attempted = result.get("items_attempted", sent)
    dropped = result.get("consolidate_dropped", 0)
    if err:
        return ("error", f"failed: {err} (sent {sent}/{attempted})")
    if sent == attempted and dropped == 0:
        return ("success", f"{sent}/{attempted} items")
    return (
        "warning",
        f"{sent}/{attempted} items"
        + (f", {dropped} consolidated-out" if dropped else ""),
    )


def _read_result_or_synthesize_error(huey_, task_id: str):
    """Read a huey task result, synthesizing an error dict if it raised.

    huey 3.0.0+ `Result.get(blocking=False)` re-raises `TaskException` whenever
    the consumer task raised. Without this guard a polling `@st.fragment` would
    exception-loop on every rerun and never clear session_state.

    Returns:
      None  — task is still pending
      dict  — terminal: either the kind's own result-dict, or a synthesized
              error dict shaped so `_format_status` returns ("error", ...).
    """
    try:
        return huey_.result(task_id, blocking=False)
    except Exception as exc:
        return {
            "error": f"task crashed: {type(exc).__name__}: {exc}",
            "items_sent": 0,
            "items_attempted": 0,
        }

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


def _read_result_or_synthesize_error(result_fn, task_id: str):
    """Call result_fn(task_id) and synthesize an error dict if it raises.

    result_fn signature: (task_id: str) -> dict | None
      None  — task is still pending
      dict  — terminal result (the kind's own result-dict or a pre-synthesized
              error dict from the HTTP client)

    The try/except is a safety net for unexpected raises (e.g. network errors
    surfaced by a non-hardened result_fn). Normal callers (jobs_client.result)
    catch internally and never raise.

    Returns:
      None  — task is still pending
      dict  — terminal: either the kind's own result-dict, or a synthesized
              error dict shaped so `_format_status` returns ("error", ...).
    """
    try:
        return result_fn(task_id)
    except Exception as exc:
        return {
            "error": f"task crashed: {type(exc).__name__}: {exc}",
            "items_sent": 0,
            "items_attempted": 0,
        }

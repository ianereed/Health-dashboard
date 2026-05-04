"""Phase 12.7 — drains state.ocr_queue into huey vision tasks; manages swap-decision UX.

Runs every minute. Responsibilities:
1. Drain state.json ocr_queue → schedule event_aggregator_vision tasks
2. If both text and vision tasks are pending: post/refresh the Slack swap-decision
3. Expire stale swap decisions (auto-resolve to "wait" after timeout)
4. Handle "interrupt" decision: log it (queue reordering not supported in SqliteHuey,
   so interrupt is informational — vision tasks run when text drains naturally)
"""
from __future__ import annotations

import importlib.util
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from huey import crontab

from jobs import huey, requires
from jobs.kinds.event_aggregator_vision import event_aggregator_vision

logger = logging.getLogger(__name__)

PROJECT = Path(__file__).resolve().parents[2] / "event-aggregator"
_SWAP_DECISION_TIMEOUT_MIN = 5


def _load_ea_state():
    """Load event-aggregator state module via importlib to avoid venv pollution."""
    spec = importlib.util.spec_from_file_location("_ea_state_tmp", PROJECT / "state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pending_task_count_by_name(task_name: str) -> int:
    """Count pending huey tasks with the given (short) function name."""
    try:
        return sum(1 for t in huey.pending() if getattr(t, "name", "").endswith(task_name))
    except Exception:
        return 0


@huey.periodic_task(crontab(minute="*"))
@requires(["fs:event-aggregator"])
def event_aggregator_decision_poller() -> dict:
    """Drain ocr_queue + manage swap-decision UX."""
    ea_state = _load_ea_state()

    scheduled_vision = 0
    interrupt_found = False
    wait_found = False

    with ea_state.locked():
        state = ea_state.load()

        # 1. Expire stale swap decisions using the public API.
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=_SWAP_DECISION_TIMEOUT_MIN)
        expired = state.expire_pending_decisions(cutoff)
        if expired:
            logger.info("decision-poller: auto-resolved %d swap decision(s) to 'wait' (timeout)", expired)

        # 2. Consume interrupt decisions.
        consumed_ids = state.consume_interrupt_decisions()
        if consumed_ids:
            interrupt_found = True
            logger.info(
                "decision-poller: consumed %d 'interrupt' decision(s) "
                "(FIFO queue; vision runs after text drains)",
                len(consumed_ids),
            )

        # Check for any remaining wait decisions.
        wait_found = any(
            info.get("decision") == "wait"
            for _, info in state.iter_swap_decisions()
        )

        # 3. Drain ocr_queue into huey vision tasks.
        while True:
            job = state.pop_ocr_job()
            if job is None:
                break
            event_aggregator_vision(job)
            scheduled_vision += 1
            logger.info("decision-poller: scheduled vision task for %s", job.get("file_path", "?"))

        ea_state.save(state)

    # 4. Post swap decision if both text and vision tasks are pending in huey.
    if scheduled_vision > 0:
        text_pending = _pending_task_count_by_name("event_aggregator_text")
        vision_pending = _pending_task_count_by_name("event_aggregator_vision")
        if text_pending > 0 and vision_pending > 0:
            _post_swap_decision_if_needed(ea_state, text_pending, vision_pending)

    return {
        "scheduled_vision": scheduled_vision,
        "interrupt_consumed": interrupt_found,
        "wait_found": wait_found,
    }


def _load_ea_notifier():
    """Load event-aggregator slack_notifier via importlib to avoid venv pollution."""
    spec = importlib.util.spec_from_file_location(
        "_ea_slack_notifier", PROJECT / "notifiers" / "slack_notifier.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_ea_tz_utils():
    """Load event-aggregator tz_utils via importlib to avoid venv pollution."""
    spec = importlib.util.spec_from_file_location("_ea_tz_utils", PROJECT / "tz_utils.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _post_swap_decision_if_needed(ea_state, text_pending: int, vision_pending: int) -> None:
    """Post a Slack swap-decision message if none is already pending."""
    try:
        with ea_state.locked():
            state = ea_state.load()
            pending_decisions = list(state.iter_swap_decisions())
            if any(info.get("decision") == "pending" for _, info in pending_decisions):
                return  # already have a pending decision
            decision_id = state.add_swap_decision("(huey queue)", text_pending)
            ea_state.save(state)

        # Trigger a dashboard render so the buttons show up.
        tz_utils = _load_ea_tz_utils()
        slack_notifier = _load_ea_notifier()
        with ea_state.locked():
            state2 = ea_state.load()
        today = tz_utils.today_user_str()
        all_items = state2.get_all_proposal_items_for_dashboard(today)
        slack_notifier.post_or_update_dashboard(all_items, state2)
        logger.info(
            "decision-poller: posted swap decision %s (text_pending=%d, vision_pending=%d)",
            decision_id, text_pending, vision_pending,
        )
    except Exception as exc:
        logger.warning("decision-poller: swap decision post failed: %s", exc)

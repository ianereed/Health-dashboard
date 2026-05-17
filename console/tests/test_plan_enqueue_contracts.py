"""Canary tests: kwargs passed by plan.py to jobs_client.enqueue() must match
the actual job function signatures. A name mismatch causes a silent TaskException
at runtime (TypeError from huey unpacking kwargs).
"""
from __future__ import annotations

import inspect


def _unwrap(task):
    """Return the underlying function from a huey @task()-decorated callable."""
    return task.func


def test_send_to_todoist_param_name() -> None:
    """plan.py passes recipe_scales= — catch renames before they reach prod."""
    from jobs.kinds.meal_planner_send_to_todoist import meal_planner_send_to_todoist

    params = inspect.signature(_unwrap(meal_planner_send_to_todoist)).parameters
    assert "recipe_scales" in params, (
        "job param renamed — update console/tabs/plan.py enqueue call to match"
    )


def test_clear_todoist_takes_no_params() -> None:
    """plan.py calls enqueue('meal_planner_clear_todoist') with no params."""
    from jobs.kinds.meal_planner_clear_todoist import meal_planner_clear_todoist

    params = inspect.signature(_unwrap(meal_planner_clear_todoist)).parameters
    assert len(params) == 0, (
        "job now requires params — update console/tabs/plan.py enqueue call to match"
    )

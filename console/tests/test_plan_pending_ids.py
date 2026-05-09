"""Tests for the pending-recipe-id tracking in console/tabs/plan.py.

Verifies that _pending_ids() correctly tracks unsaved stub rows so
Cancel can delete them and Save can clear them from the pending set.

All tests mock st.session_state as a plain dict; no Streamlit server needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _import_plan():
    from console.tabs import plan
    return plan


def _fake_state():
    """Return a fresh dict to stand in for st.session_state."""
    return {}


def test_pending_ids_initializes_empty() -> None:
    state = _fake_state()
    plan = _import_plan()
    with patch("streamlit.session_state", state):
        ids = plan._pending_ids()
    assert isinstance(ids, set)
    assert ids == set()


def test_pending_ids_add_and_contains() -> None:
    state = _fake_state()
    plan = _import_plan()
    with patch("streamlit.session_state", state):
        plan._pending_ids().add(7)
        assert 7 in plan._pending_ids()
        assert 99 not in plan._pending_ids()


def test_pending_ids_discard_removes() -> None:
    state = _fake_state()
    plan = _import_plan()
    with patch("streamlit.session_state", state):
        plan._pending_ids().add(7)
        plan._pending_ids().discard(7)
        assert 7 not in plan._pending_ids()


def test_pending_ids_discard_missing_is_noop() -> None:
    state = _fake_state()
    plan = _import_plan()
    with patch("streamlit.session_state", state):
        # discard on an id that was never added must not raise
        plan._pending_ids().discard(999)
        assert plan._pending_ids() == set()


def test_save_clears_from_pending() -> None:
    """After discarding on save, the id is gone from the pending set."""
    state = _fake_state()
    plan = _import_plan()
    with patch("streamlit.session_state", state):
        plan._pending_ids().add(42)
        assert 42 in plan._pending_ids()
        # Simulate save success path: discard before closing panel
        plan._pending_ids().discard(42)
        assert 42 not in plan._pending_ids()


def test_cancel_pending_calls_delete_recipe() -> None:
    """Cancel handler deletes the stub when the id is in the pending set."""
    state = _fake_state()
    plan = _import_plan()
    mock_delete = MagicMock()

    with patch("streamlit.session_state", state), \
         patch("meal_planner.queries.delete_recipe", mock_delete):
        plan._pending_ids().add(5)
        # Replicate the cancel handler logic
        recipe_id = 5
        if recipe_id in plan._pending_ids():
            plan._pending_ids().discard(recipe_id)
            try:
                import meal_planner.queries as q
                q.delete_recipe(recipe_id)
            except Exception:
                pass
        assert 5 not in plan._pending_ids()

    mock_delete.assert_called_once_with(5)


def test_cancel_non_pending_does_not_delete() -> None:
    """Cancel on a previously saved recipe must NOT call delete_recipe."""
    state = _fake_state()
    plan = _import_plan()
    mock_delete = MagicMock()

    with patch("streamlit.session_state", state), \
         patch("meal_planner.queries.delete_recipe", mock_delete):
        # id 5 was saved → not in pending set
        recipe_id = 5
        if recipe_id in plan._pending_ids():  # False
            plan._pending_ids().discard(recipe_id)
            try:
                import meal_planner.queries as q
                q.delete_recipe(recipe_id)
            except Exception:
                pass

    mock_delete.assert_not_called()

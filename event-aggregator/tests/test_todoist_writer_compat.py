"""Back-compat + new-feature tests for todoist_writer.create_task (Phase 14.4).

Calling create_task without the new kw-only params must produce the exact same
payload shape as before the extension. Calling with section_id / labels must
produce the new shape. All HTTP is mocked.
"""
from __future__ import annotations

from models import CandidateTodo
from writers import todoist_writer


def _make_todo(**kwargs) -> CandidateTodo:
    defaults = dict(
        title="Buy milk",
        source="test",
        source_id="abc123",
        source_url=None,
        confidence=0.9,
        context=None,
        due_date=None,
        priority="normal",
    )
    defaults.update(kwargs)
    return CandidateTodo(**defaults)


def _capture_payload(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    class FakeResp:
        def raise_for_status(self) -> None:
            pass
        def json(self) -> dict:
            return {"id": "task-1"}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.append(json or {})
        return FakeResp()

    monkeypatch.setattr("writers.todoist_writer.requests.post", fake_post)
    return captured


# ---------------------------------------------------------------------------
# Back-compat: no new kwargs → unchanged payload
# ---------------------------------------------------------------------------

def test_no_new_kwargs_labels_is_event_aggregator(monkeypatch) -> None:
    """Calling create_task without labels= must produce labels=['event-aggregator']."""
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(token="tok", project_id=None, todo=todo)
    assert len(captured) == 1
    assert captured[0]["labels"] == ["event-aggregator"]


def test_no_new_kwargs_no_section_id_in_payload(monkeypatch) -> None:
    """Calling create_task without section_id= must NOT include section_id in payload."""
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(token="tok", project_id=None, todo=todo)
    assert "section_id" not in captured[0]


def test_no_new_kwargs_project_id_routed(monkeypatch) -> None:
    """project_id is still forwarded correctly when no new kwargs are given."""
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(token="tok", project_id="proj-99", todo=todo)
    assert captured[0].get("project_id") == "proj-99"


def test_existing_signature_bind_unchanged() -> None:
    """Existing callers bind (token, project_id, todo, dry_run) — must still work."""
    import inspect
    sig = inspect.signature(todoist_writer.create_task)
    sig.bind("tok", "proj", _make_todo(), False)


# ---------------------------------------------------------------------------
# New kwargs: section_id and labels pass-through
# ---------------------------------------------------------------------------

def test_section_id_included_in_payload(monkeypatch) -> None:
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(
        token="tok", project_id="proj-1", todo=todo, section_id="sec-42"
    )
    assert captured[0].get("section_id") == "sec-42"


def test_labels_override_replaces_default(monkeypatch) -> None:
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(
        token="tok", project_id=None, todo=todo, labels=["meal-planner"]
    )
    assert captured[0]["labels"] == ["meal-planner"]


def test_labels_none_means_event_aggregator(monkeypatch) -> None:
    """Passing labels=None explicitly must still produce the back-compat default."""
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(
        token="tok", project_id=None, todo=todo, labels=None
    )
    assert captured[0]["labels"] == ["event-aggregator"]


def test_section_id_none_omitted_from_payload(monkeypatch) -> None:
    """section_id=None (explicit) must NOT add section_id to the payload."""
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(
        token="tok", project_id=None, todo=todo, section_id=None
    )
    assert "section_id" not in captured[0]


def test_both_new_kwargs_together(monkeypatch) -> None:
    """section_id + labels both present → both in payload."""
    captured = _capture_payload(monkeypatch)
    todo = _make_todo()
    todoist_writer.create_task(
        token="tok",
        project_id="proj-1",
        todo=todo,
        section_id="sec-7",
        labels=["meal-planner"],
    )
    assert captured[0].get("section_id") == "sec-7"
    assert captured[0]["labels"] == ["meal-planner"]

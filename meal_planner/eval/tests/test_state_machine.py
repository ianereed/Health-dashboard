"""Tests for the runs.jsonl state machine: _resume_from, _summarize."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from bake_off import (  # noqa: E402
    _RUNS_SCHEMA_VERSION,
    RunRow,
    _append_row,
    _resume_from,
    _summarize,
)


def test_resume_skips_terminal_rows(tmp_path):
    """_resume_from returns only (model, photo) pairs at terminal status."""
    _append_row(tmp_path, RunRow(model="modelA", photo="photo1.jpg", status="parsed_ok"))
    _append_row(tmp_path, RunRow(model="modelA", photo="photo2.jpg", status="pending"))

    done = _resume_from(tmp_path)
    assert ("modelA", "photo1.jpg") in done
    assert ("modelA", "photo2.jpg") not in done
    assert len(done) == 1


def test_schema_version_mismatch_refuses(tmp_path):
    """_resume_from raises RuntimeError when schema_version differs from current."""
    runs_path = tmp_path / "runs.jsonl"
    bad_row = {"schema_version": 99, "model": "m", "photo": "p.jpg", "status": "scored"}
    runs_path.write_text(json.dumps(bad_row) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="schema_version mismatch"):
        _resume_from(tmp_path)


def test_summarize_aggregates(tmp_path):
    """_summarize computes correct means across 3 scored rows for one model."""
    scores = [
        {"title_accuracy": 1.0, "ingredient_f1": 0.8, "parse_correctness": 0.9,
         "structural_validity": True, "errors": []},
        {"title_accuracy": 0.0, "ingredient_f1": 0.6, "parse_correctness": 0.7,
         "structural_validity": True, "errors": []},
        {"title_accuracy": 1.0, "ingredient_f1": 1.0, "parse_correctness": 1.0,
         "structural_validity": False, "errors": ["ingredients_not_list"]},
    ]
    latencies = [1.0, 2.0, 3.0]

    for i, (score, lat) in enumerate(zip(scores, latencies)):
        _append_row(tmp_path, RunRow(
            model="modelA",
            photo=f"photo{i}.jpg",
            status="scored",
            latency_s=lat,
            score=score,
        ))

    summary = _summarize(tmp_path)

    assert summary["schema_version"] == _RUNS_SCHEMA_VERSION
    assert len(summary["models"]) == 1

    m = summary["models"][0]
    assert m["model"] == "modelA"
    assert m["n_scored"] == 3
    assert abs(m["title_accuracy_mean"] - (1.0 + 0.0 + 1.0) / 3) < 1e-9
    assert abs(m["ingredient_f1_mean"] - (0.8 + 0.6 + 1.0) / 3) < 1e-9
    # structural_validity_rate = 2/3
    assert abs(m["structural_validity_rate"] - 2 / 3) < 1e-9
    # latency p50 = median([1,2,3]) = 2.0
    assert m["latency_p50"] == 2.0

    # summary.json written to disk
    assert (tmp_path / "summary.json").exists()

"""Tests for the runs.jsonl state machine: _resume_from, _summarize."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

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
    assert m["latency_p50_warm"] == 2.0

    # summary.json written to disk
    assert (tmp_path / "summary.json").exists()


def test_summarize_includes_bench_metadata(tmp_path, monkeypatch):
    """_summarize emits all 4 bench-level metadata fields when called with context."""
    _append_row(tmp_path, RunRow(
        model="qwen2.5vl:3b",
        photo="photo1.jpg",
        status="scored",
        latency_s=5.0,
        cold_load_s=8.0,
        score={
            "title_accuracy": 1.0, "ingredient_f1": 0.9, "parse_correctness": 1.0,
            "structural_validity": True, "errors": [],
        },
    ))

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    photo = corpus_dir / "photo1.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0")
    golden = corpus_dir / "photo1.golden.json"
    golden.write_text('{"title": "Test", "ingredients": []}', encoding="utf-8")
    pairs = [(photo, golden)]

    def mock_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        cmd_str = " ".join(str(c) for c in cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "abc1234def5678abc1234def5678abc1234def5678\n"
        elif "ollama" in cmd_str and "list" in cmd_str:
            result.stdout = (
                "NAME              ID              SIZE      MODIFIED\n"
                "qwen2.5vl:3b      fb90415cde1e    3.2 GB    2 hours ago\n"
            )
        else:
            result.stdout = ""
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    summary = _summarize(
        tmp_path,
        pairs=pairs,
        ran_at="2026-05-05T15:00:00+00:00",
        peak_rss_by_model={"qwen2.5vl:3b": 3.2},
    )

    assert summary["git_commit"] is not None
    assert summary["corpus_checksum"] is not None
    assert summary["ran_at"] == "2026-05-05T15:00:00+00:00"
    assert summary["ollama_model_digests"] is not None
    assert "qwen2.5vl:3b" in summary["ollama_model_digests"]
    assert summary["models"][0]["peak_rss_gb"] == 3.2

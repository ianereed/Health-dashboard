"""Tests for warm-reuse (cmd_run_warm + keep_alive plumbing) in bake_off.py."""
from __future__ import annotations

import json
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import bake_off
from bake_off import _ollama_one_call


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {
            "response": json.dumps({"title": "Test Recipe", "ingredients": [], "tags": []}),
            "eval_count": 10,
        }

    def json(self) -> dict:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload)


def _make_corpus(tmp_path: pathlib.Path, n: int = 3) -> pathlib.Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(1, n + 1):
        photo = corpus / f"IMG_{i:04d}.jpg"
        photo.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)  # minimal JPEG
        golden = corpus / f"IMG_{i:04d}.golden.json"
        golden.write_text(json.dumps({
            "title": f"Recipe {i}",
            "ingredients": [{"qty": "1", "unit": "cup", "name": "flour"}],
            "tags": [],
        }))
    return corpus


def test_keep_alive_propagates_through_one_call(tmp_path: pathlib.Path) -> None:
    """_ollama_one_call must send the keep_alive value in the request body."""
    captured: dict = {}

    def fake_post(url: str, json: dict | None = None, **kwargs):
        captured["body"] = json
        return _FakeResponse()

    with patch("requests.post", side_effect=fake_post):
        _ollama_one_call(
            "minicpm-v:8b",
            "aGVsbG8=",  # dummy base64
            "test prompt",
            "http://localhost:11434",
            4096,
            keep_alive="300s",
        )

    assert "body" in captured, "requests.post was never called"
    assert captured["body"]["keep_alive"] == "300s", (
        f"expected keep_alive='300s', got {captured['body'].get('keep_alive')!r}"
    )


def test_warm_reuse_unloads_once(tmp_path: pathlib.Path) -> None:
    """cmd_run_warm must call _unload_ollama exactly once, then send keep_alive='300s' on every call."""
    corpus = _make_corpus(tmp_path, n=3)
    out = tmp_path / "out"

    unload_calls: list[str] = []
    post_keep_alives: list = []

    def fake_unload(model: str, base_url: str) -> None:
        unload_calls.append(model)

    def fake_post(url: str, json: dict | None = None, **kwargs):
        if json and "keep_alive" in json:
            post_keep_alives.append(json["keep_alive"])
        payload = {
            "response": __import__("json").dumps({"title": "Test", "ingredients": [], "tags": []}),
            "eval_count": 5,
        }
        return _FakeResponse(200, payload)

    args = MagicMock()
    args.corpus = str(corpus)
    args.model = "minicpm-v:8b"
    args.out = str(out)
    args.ollama_base_url = "http://localhost:11434"
    args.num_ctx = None
    args.keep_alive_seconds = 300

    with patch.object(bake_off, "_unload_ollama", side_effect=fake_unload), \
         patch("requests.post", side_effect=fake_post):
        result = bake_off.cmd_run_warm(args)

    assert result == 0, f"cmd_run_warm returned non-zero: {result}"
    assert len(unload_calls) == 1, f"expected 1 unload call, got {len(unload_calls)}"
    # Each photo gets at least one POST (initial call); 3 photos = at least 3 POSTs
    inference_calls = [ka for ka in post_keep_alives if ka != 0]
    assert len(inference_calls) == 3, (
        f"expected 3 inference POST calls with keep_alive, got {len(inference_calls)}: {post_keep_alives}"
    )
    assert all(ka == "300s" for ka in inference_calls), (
        f"not all inference calls used keep_alive='300s': {inference_calls}"
    )


def test_warm_first_records_cold_load(tmp_path: pathlib.Path) -> None:
    """Photo 0: cold_load_s set + is_warm=False + latency_s=None.
    Photos 1+: is_warm=True + latency_s set + cold_load_s=None."""
    corpus = _make_corpus(tmp_path, n=3)
    out = tmp_path / "out"

    def fake_post(url: str, json: dict | None = None, **kwargs):
        if json and json.get("keep_alive") == 0:
            return _FakeResponse(200, {})
        payload = {
            "response": __import__("json").dumps({"title": "Test", "ingredients": [], "tags": []}),
            "eval_count": 5,
        }
        return _FakeResponse(200, payload)

    args = MagicMock()
    args.corpus = str(corpus)
    args.model = "minicpm-v:8b"
    args.out = str(out)
    args.ollama_base_url = "http://localhost:11434"
    args.num_ctx = None
    args.keep_alive_seconds = 300

    with patch.object(bake_off, "_unload_ollama", return_value=None), \
         patch("requests.post", side_effect=fake_post):
        bake_off.cmd_run_warm(args)

    runs_path = out / "runs.jsonl"
    assert runs_path.exists()

    scored = [
        json.loads(line)
        for line in runs_path.read_text().splitlines()
        if line.strip() and json.loads(line).get("status") == "scored"
    ]
    assert len(scored) == 3, f"expected 3 scored rows, got {len(scored)}"

    cold_row = scored[0]
    assert cold_row.get("is_warm") is False, f"photo 0 should have is_warm=False, got {cold_row.get('is_warm')!r}"
    assert cold_row.get("cold_load_s") is not None, "photo 0 should have cold_load_s set"
    assert cold_row.get("latency_s") is None, "photo 0 latency_s should be None"

    for i, warm_row in enumerate(scored[1:], start=1):
        assert warm_row.get("is_warm") is True, (
            f"photo {i} should have is_warm=True, got {warm_row.get('is_warm')!r}"
        )
        assert warm_row.get("cold_load_s") is None, (
            f"photo {i} cold_load_s should be None, got {warm_row.get('cold_load_s')!r}"
        )
        assert warm_row.get("latency_s") is not None, (
            f"photo {i} should have latency_s set"
        )

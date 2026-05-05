"""
bake_off.py — Phase 15 recipe-photo LLM bake-off.

Subcommands:
  preflight   Check mini readiness (disk, memory, Ollama model tags, Gemini auth).
              Exits 0 if all checks pass, non-zero otherwise.
  run         Run the bake-off: call each model on each photo in the corpus,
              score results, write runs.jsonl + summary.json to --out dir.

Provider strings accepted by --models:
  ollama:<tag>                     Ollama on localhost (e.g. ollama:qwen2.5vl:7b)
  gemini-<variant>                 Gemini free tier (e.g. gemini-2.5-flash)
  llama-3.2-90b-vision-preview     Groq free tier (requires GROQ_API_KEY in env)

Known Ollama vision tags: qwen2.5vl:7b, qwen2.5vl:3b, llama3.2-vision:11b, minicpm-v:8b
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import requests
import yaml

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_SYNONYMS_PATH = pathlib.Path(__file__).parent / "synonyms.yml"
_RESULTS_ROOT = pathlib.Path(__file__).parent / "results"

_KNOWN_OLLAMA_VISION_TAGS = frozenset({
    "qwen2.5vl:7b",
    "qwen2.5vl:3b",
    "llama3.2-vision:11b",
    "minicpm-v:8b",
})

_SYNONYMS: dict | None = None


def _load_synonyms() -> dict:
    global _SYNONYMS
    if _SYNONYMS is None:
        with open(_SYNONYMS_PATH, encoding="utf-8") as f:
            _SYNONYMS = yaml.safe_load(f)
    return _SYNONYMS


def _build_synonym_map(data: dict) -> dict[str, str]:
    """Return {alternate: canonical} for all synonym groups."""
    mapping: dict[str, str] = {}
    for group in data.get("synonyms", []):
        parts = [p.strip() for p in group.split(";")]
        if not parts:
            continue
        canonical = parts[0]
        for alternate in parts[1:]:
            if alternate:
                mapping[alternate] = canonical
    return mapping


def _normalize_ingredient_name(name: str, synonyms: Optional[dict] = None) -> str:
    """Lowercase, strip punctuation, trivially singularize, apply synonym map."""
    if synonyms is None:
        synonyms = _load_synonyms()
    mapping = _build_synonym_map(synonyms)

    # Lowercase + strip leading/trailing punctuation/whitespace
    normalized = name.lower().strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized).strip()
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)

    # Trivial singularization: drop trailing 's' if len > 3 and not ending in 'ss'
    if len(normalized) > 3 and normalized.endswith("s") and not normalized.endswith("ss"):
        normalized = normalized[:-1]

    return mapping.get(normalized, normalized)


def _casefold_strip_punct(s: str) -> str:
    """Casefold and strip all non-word punctuation for title comparison."""
    return re.sub(r"[^\w\s]", "", s).casefold().strip()


def _normalize_qty(q: Optional[str], unicode_fractions: dict) -> Optional[str]:
    """Normalize a quantity string to a canonical form for comparison."""
    if q is None:
        return None

    s = q.strip()

    # Special string values → None
    if s.lower() in {"to taste", "for serving", "as needed", ""}:
        return None

    # Replace unicode fractions
    for frac, val in unicode_fractions.items():
        s = s.replace(frac, str(val))

    # Mixed number: "<integer> <fraction>" e.g. "1 1/2" or "6 1/2"
    mixed = re.match(r"^(\d+)\s+(\d+)/(\d+)$", s)
    if mixed:
        whole = int(mixed.group(1))
        num = int(mixed.group(2))
        den = int(mixed.group(3))
        val = whole + num / den
        # Return as clean decimal string, stripping trailing zeros
        return _float_to_clean(val)

    # Range: "2-3" or "2 to 3" or "1/3-1/2"
    range_m = re.match(r"^(.+?)\s*(?:-|to)\s*(.+)$", s)
    if range_m:
        lo_raw = range_m.group(1).strip()
        hi_raw = range_m.group(2).strip()
        lo = _parse_numeric(lo_raw)
        hi = _parse_numeric(hi_raw)
        if lo is not None and hi is not None:
            return f"{_float_to_clean(lo)}-{_float_to_clean(hi)}"

    # Single numeric
    val = _parse_numeric(s)
    if val is not None:
        return _float_to_clean(val)

    # Passthrough (handles things like "1 20oz can", non-numeric units embedded)
    return s


def _parse_numeric(s: str) -> Optional[float]:
    """Parse a string as int, float, or fraction (e.g. '1/2'). Returns None if unparseable."""
    s = s.strip()
    frac_m = re.match(r"^(\d+)/(\d+)$", s)
    if frac_m:
        return int(frac_m.group(1)) / int(frac_m.group(2))
    try:
        return float(s)
    except ValueError:
        return None


def _float_to_clean(val: float) -> str:
    """Format float as clean string: integer if whole, else minimal decimal."""
    if val == int(val):
        return str(int(val))
    # Up to 3 decimal places, strip trailing zeros
    return f"{val:.3f}".rstrip("0").rstrip(".")


def _qty_matches(eq: Optional[str], gq: Optional[str], unicode_fractions: dict) -> bool:
    """Return True if extracted qty matches golden qty, including range-vs-scalar rules."""
    ne = _normalize_qty(eq, unicode_fractions)
    ng = _normalize_qty(gq, unicode_fractions)

    if ne == ng:
        return True

    # Range-vs-scalar: if one is a range and the other is a scalar within it
    def _as_range(v: Optional[str]):
        if v is None:
            return None
        m = re.match(r"^(.+)-(.+)$", v)
        if m:
            lo = _parse_numeric(m.group(1))
            hi = _parse_numeric(m.group(2))
            if lo is not None and hi is not None:
                return (lo, hi)
        return None

    def _as_scalar(v: Optional[str]):
        if v is None:
            return None
        return _parse_numeric(v)

    re_range = _as_range(ne)
    rg_range = _as_range(ng)

    if re_range and ng is not None:
        scalar = _as_scalar(ng)
        if scalar is not None and re_range[0] <= scalar <= re_range[1]:
            return True
    if rg_range and ne is not None:
        scalar = _as_scalar(ne)
        if scalar is not None and rg_range[0] <= scalar <= rg_range[1]:
            return True

    return False


def _normalize_unit(u: Optional[str]) -> Optional[str]:
    """Normalize a unit string to a canonical form."""
    if u is None:
        return None

    s = u.lower().strip().rstrip(".")

    _UNIT_MAP = {
        "cup": "cup", "cups": "cup", "c": "cup",
        "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbs": "tbsp", "t": "tbsp",
        "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp",
        "ounce": "oz", "ounces": "oz", "oz": "oz",
        "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
        "gram": "g", "grams": "g", "g": "g",
        "kilogram": "kg", "kg": "kg",
        "milliliter": "ml", "ml": "ml",
        "liter": "l", "l": "l",
    }
    return _UNIT_MAP.get(s, s)


def _score(extracted: dict, golden: dict, synonyms: dict, unicode_fractions: dict) -> dict:
    """Score extracted recipe output against golden.

    Returns:
        title_accuracy, ingredient_f1, ingredient_precision, ingredient_recall,
        parse_correctness, structural_validity, errors
    """
    errors: list[str] = []

    # Structural validity check
    def _is_valid_structure(d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        if not isinstance(d.get("title"), str):
            errors.append("title_not_str")
            return False
        if not isinstance(d.get("ingredients"), list):
            errors.append("ingredients_not_list")
            return False
        if not isinstance(d.get("tags"), list):
            errors.append("tags_not_list")
            return False
        for item in d["ingredients"]:
            if not isinstance(item, dict):
                errors.append("ingredient_item_not_dict")
                return False
            for k in ("qty", "unit", "name"):
                if k not in item:
                    errors.append(f"ingredient_missing_key_{k}")
                    return False
        return True

    if not _is_valid_structure(extracted):
        return {
            "title_accuracy": 0.0,
            "ingredient_f1": 0.0,
            "ingredient_precision": 0.0,
            "ingredient_recall": 0.0,
            "parse_correctness": 0.0,
            "structural_validity": False,
            "errors": errors,
        }

    # Title accuracy
    title_accuracy = (
        1.0
        if _casefold_strip_punct(extracted["title"]) == _casefold_strip_punct(golden["title"])
        else 0.0
    )

    # Build normalized name sets (set-F1: dedupe by name)
    def _name_set(ingredients: list[dict]) -> set[str]:
        return {_normalize_ingredient_name(item["name"], synonyms) for item in ingredients}

    e_names = _name_set(extracted["ingredients"])
    g_names = _name_set(golden["ingredients"])

    overlap = e_names & g_names

    if len(e_names) == 0 and len(g_names) == 0:
        precision = 1.0
        recall = 1.0
    else:
        precision = len(overlap) / len(e_names) if e_names else 0.0
        recall = len(overlap) / len(g_names) if g_names else 0.0

    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Parse correctness: for each matched name, compare qty+unit
    parse_scores: list[float] = []
    for name in overlap:
        # Find first matching ingredient in each (set-dedup means one representative)
        e_item = next(
            (i for i in extracted["ingredients"]
             if _normalize_ingredient_name(i["name"], synonyms) == name),
            None,
        )
        g_item = next(
            (i for i in golden["ingredients"]
             if _normalize_ingredient_name(i["name"], synonyms) == name),
            None,
        )
        if e_item is None or g_item is None:
            continue

        qty_match = _qty_matches(e_item.get("qty"), g_item.get("qty"), unicode_fractions)
        unit_match = _normalize_unit(e_item.get("unit")) == _normalize_unit(g_item.get("unit"))
        parse_scores.append((float(qty_match) + float(unit_match)) / 2.0)

    parse_correctness = statistics.mean(parse_scores) if parse_scores else 0.0

    return {
        "title_accuracy": title_accuracy,
        "ingredient_f1": f1,
        "ingredient_precision": precision,
        "ingredient_recall": recall,
        "parse_correctness": parse_correctness,
        "structural_validity": True,
        "errors": errors,
    }


def _load_corpus(corpus_dir: pathlib.Path) -> list[tuple[pathlib.Path, dict]]:
    """Walk corpus_dir, pair each photo with its .golden.json sibling.

    Uses case-insensitive suffix matching to handle .JPG (uppercase) from iPhone.
    Skips unmatched photos with a stderr warning.
    """
    pairs: list[tuple[pathlib.Path, dict]] = []
    for p in sorted(corpus_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        # .golden.json lives next to the photo, named by stem (case-sensitive on HFS+ display)
        golden_path = p.parent / f"{p.stem}.golden.json"
        if not golden_path.exists():
            print(f"warning: no golden for {p.name}, skipping", file=sys.stderr)
            continue
        with golden_path.open(encoding="utf-8") as f:
            golden = json.load(f)
        pairs.append((p, golden))
    return pairs


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset({
    "parsed_ok", "parse_fail", "provider_error", "budget_exceeded", "scored"
})

_RUNS_SCHEMA_VERSION = 1


@dataclass
class RunRow:
    schema_version: int = _RUNS_SCHEMA_VERSION
    model: str = ""
    photo: str = ""
    status: str = "pending"
    started_at: str = ""
    ended_at: Optional[str] = None
    latency_s: Optional[float] = None
    cold_load_s: Optional[float] = None
    tokens_used: Optional[int] = None
    extracted: Optional[dict] = None
    error: Optional[str] = None
    score: Optional[dict] = None


def _append_row(out_dir: pathlib.Path, row: RunRow) -> None:
    runs_path = out_dir / "runs.jsonl"
    with runs_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(row)) + "\n")


def _resume_from(out_dir: pathlib.Path) -> set[tuple[str, str]]:
    """Read runs.jsonl, return set of (model, photo_basename) at terminal status.

    Raises RuntimeError on schema_version mismatch.
    """
    runs_path = out_dir / "runs.jsonl"
    if not runs_path.exists():
        return set()

    done: set[tuple[str, str]] = set()
    with runs_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            sv = row.get("schema_version")
            if sv != _RUNS_SCHEMA_VERSION:
                raise RuntimeError(
                    f"schema_version mismatch: expected {_RUNS_SCHEMA_VERSION}, got {sv}. "
                    "Cannot resume across schema versions."
                )
            if row.get("status") in _TERMINAL_STATUSES:
                done.add((row["model"], row["photo"]))
    return done


def _resolve_resume_dir(arg: str, results_root: pathlib.Path) -> pathlib.Path:
    """Resolve --resume-from argument to a concrete directory.

    'latest' → most-recent dated subdir under results_root.
    Any other string → treat as a direct path.
    Raises if neither exists.
    """
    if arg == "latest":
        if not results_root.exists():
            raise FileNotFoundError(f"results root does not exist: {results_root}")
        subdirs = sorted(
            [d for d in results_root.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        if not subdirs:
            raise FileNotFoundError(f"no subdirs found under {results_root}")
        return subdirs[-1]

    p = pathlib.Path(arg)
    if not p.exists():
        raise FileNotFoundError(f"resume-from path does not exist: {p}")
    return p


def _summarize(out_dir: pathlib.Path) -> dict:
    """Read runs.jsonl, compute per-model stats, write summary.json."""
    runs_path = out_dir / "runs.jsonl"
    rows: list[dict] = []
    with runs_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # Group by model
    by_model: dict[str, list[dict]] = {}
    for row in rows:
        m = row["model"]
        by_model.setdefault(m, []).append(row)

    model_stats: list[dict] = []
    for model, model_rows in by_model.items():
        scored = [r for r in model_rows if r.get("status") == "scored" and r.get("score")]

        def _mean_key(key: str) -> Optional[float]:
            vals = [r["score"][key] for r in scored if r["score"].get(key) is not None]
            return statistics.mean(vals) if vals else None

        latencies = [r["latency_s"] for r in model_rows if r.get("latency_s") is not None]
        cold_loads = [r["cold_load_s"] for r in model_rows if r.get("cold_load_s") is not None]

        def _p50(vals: list[float]) -> Optional[float]:
            return statistics.median(vals) if vals else None

        def _p95(vals: list[float]) -> Optional[float]:
            if not vals:
                return None
            idx = max(0, int(len(vals) * 0.95) - 1)
            return sorted(vals)[idx]

        errors = [
            {"photo": r["photo"], "error": r.get("error")}
            for r in model_rows
            if r.get("error")
        ]

        n_scored = len(scored)
        validity_rate = (
            sum(1 for r in scored if r["score"].get("structural_validity")) / n_scored
            if n_scored else None
        )

        model_stats.append({
            "model": model,
            "n_scored": n_scored,
            "title_accuracy_mean": _mean_key("title_accuracy"),
            "ingredient_f1_mean": _mean_key("ingredient_f1"),
            "parse_correctness_mean": _mean_key("parse_correctness"),
            "structural_validity_rate": validity_rate,
            "latency_p50": _p50(latencies),
            "latency_p95": _p95(latencies),
            "cold_load_p50": _p50(cold_loads),
            "cold_load_p95": _p95(cold_loads),
            "errors": errors,
        })

    summary = {
        "schema_version": _RUNS_SCHEMA_VERSION,
        "models": model_stats,
    }
    summary_path = out_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


# ---------------------------------------------------------------------------
# Ollama vision adapter
# ---------------------------------------------------------------------------

_PROMPT_PATH = pathlib.Path(__file__).parent / "recipe_extraction_prompt.txt"
_PROMPT_TEXT: str | None = None


def _load_prompt() -> str:
    global _PROMPT_TEXT
    if _PROMPT_TEXT is None:
        _PROMPT_TEXT = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return _PROMPT_TEXT


def _unload_ollama(model: str, base_url: str) -> None:
    """Unload model from GPU. Mirrors Mac-mini/benchmark_models.py:_unload (line 142)."""
    try:
        requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10,
        )
    except Exception:
        pass
    time.sleep(2)


def _call_ollama_vision(
    model: str,
    image_path: pathlib.Path,
    prompt: str,
    base_url: str = "http://localhost:11434",
) -> tuple[dict | None, dict]:
    """Call Ollama vision API with a single image. Returns (parsed_json_or_None, metadata).

    metadata keys: latency_s, cold_load_s (set by _cold_call_ollama), eval_count,
    raw_response (the full Ollama response body text).

    HTTP errors (including 429) are never collapsed into a parsed result — they always
    return (None, metadata). This is the regression gate for the 2026-05-04 incident
    where a 429 with empty body silently produced {}.
    """
    with image_path.open("rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("ascii")

    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "images": [image_b64],
        "keep_alive": "10s",
        "options": {"temperature": 0.1},
    }

    metadata: dict = {
        "latency_s": None,
        "cold_load_s": None,
        "eval_count": None,
        "raw_response": None,
    }

    t0 = time.monotonic()
    try:
        r = requests.post(f"{base_url}/api/generate", json=body, timeout=180)
    except requests.RequestException as exc:
        metadata["latency_s"] = round(time.monotonic() - t0, 3)
        metadata["raw_response"] = str(exc)
        return None, metadata

    metadata["latency_s"] = round(time.monotonic() - t0, 3)

    if r.status_code != 200:
        # Do NOT attempt to parse non-200 responses as JSON.
        metadata["raw_response"] = f"HTTP {r.status_code}: {r.text[:1000]}"
        return None, metadata

    raw_text = r.text
    metadata["raw_response"] = raw_text

    try:
        resp_json = r.json()
    except ValueError:
        return None, metadata

    metadata["eval_count"] = resp_json.get("eval_count")
    response_text = resp_json.get("response", "")

    try:
        parsed = json.loads(response_text)
    except (json.JSONDecodeError, ValueError):
        return None, metadata

    if not isinstance(parsed, dict):
        return None, metadata

    return parsed, metadata


def _cold_call_ollama(
    model: str,
    image_path: pathlib.Path,
    prompt: str,
    base_url: str = "http://localhost:11434",
) -> tuple[dict | None, dict]:
    """Unload model then call — measures cold-start latency.

    Mirrors Mac-mini/benchmark_models.py:_cold_load (line 243).
    cold_load_s includes the 2s sleep from _unload_ollama plus inference time.
    """
    t0 = time.monotonic()
    _unload_ollama(model, base_url)
    parsed, metadata = _call_ollama_vision(model, image_path, prompt, base_url)
    metadata["cold_load_s"] = round(time.monotonic() - t0, 3)
    return parsed, metadata


# ---------------------------------------------------------------------------
# Preflight helpers
# ---------------------------------------------------------------------------

def _parse_df_avail_gb(df_output: str) -> float | None:
    """Parse available GB from `df -h` stdout. Returns None if unparseable."""
    lines = df_output.strip().splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) < 4:
            continue
        avail = parts[3]
        try:
            if avail.endswith("Gi") or avail.endswith("G"):
                return float(avail.rstrip("GiB"))
            if avail.endswith("Ti") or avail.endswith("T"):
                return float(avail.rstrip("TiB")) * 1024
            if avail.endswith("Mi") or avail.endswith("M"):
                return float(avail.rstrip("MiB")) / 1024
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def _validate_models(models: list[str]) -> list[str]:
    """Return list of invalid provider strings, empty if all valid."""
    invalid = []
    for model in models:
        if (
            model.startswith("ollama:")
            or model.startswith("gemini-")
            or model == "llama-3.2-90b-vision-preview"
            or model in _KNOWN_OLLAMA_VISION_TAGS
        ):
            continue
        invalid.append(model)
    return invalid


def cmd_preflight(args: argparse.Namespace) -> int:
    ssh_host = args.ssh_host
    models_to_check = [m.strip() for m in args.models_to_check.split(",") if m.strip()]
    failed = False

    # 1. Disk check: ~/.ollama volume must have >=35GB free
    r = subprocess.run(
        ["ssh", ssh_host, "df -h ~/.ollama"],
        capture_output=True, text=True, timeout=20,
    )
    if r.returncode != 0:
        print(f"preflight FAIL: df -h ~/.ollama failed: {r.stderr.strip()}", file=sys.stderr)
        failed = True
    else:
        avail_gb = _parse_df_avail_gb(r.stdout)
        if avail_gb is None or avail_gb < 35:
            gb_str = f"{avail_gb:.0f}GB" if avail_gb is not None else "unknown"
            print(
                f"preflight FAIL: disk space too low ({gb_str} available, need >=35GB). "
                "Free space on the ~/.ollama volume before running.",
                file=sys.stderr,
            )
            failed = True

    # 2. Shared workers must be unloaded before the bench
    _WORKER_LABELS = (
        "com.home-tools.jobs-consumer",
        "com.home-tools.dispatcher",
    )
    loaded_workers = []
    for label in _WORKER_LABELS:
        r = subprocess.run(
            ["ssh", ssh_host, f"launchctl print gui/501/{label}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            loaded_workers.append(label)

    if loaded_workers:
        print(
            "preflight FAIL: shared workers are loaded. Run these commands on the mini first:",
            file=sys.stderr,
        )
        for label in loaded_workers:
            print(f"  launchctl bootout gui/501/{label}", file=sys.stderr)
        failed = True

    # 3. Memory pressure must be Normal
    r = subprocess.run(
        ["ssh", ssh_host, "memory_pressure"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0 or "Normal" not in r.stdout:
        print(
            "preflight FAIL: memory pressure is not Normal. "
            "Wait for other processes to finish before running the bench.",
            file=sys.stderr,
        )
        failed = True

    # 4. Ollama model tags must be present
    r = subprocess.run(
        ["ssh", ssh_host, "ollama list"],
        capture_output=True, text=True, timeout=20,
    )
    if r.returncode != 0:
        print(f"preflight FAIL: could not list Ollama models: {r.stderr.strip()}", file=sys.stderr)
        failed = True
    else:
        missing = [m for m in models_to_check if m not in r.stdout]
        if missing:
            print("preflight FAIL: missing Ollama models. Pull them first:", file=sys.stderr)
            for m in missing:
                print(f"  ollama pull {m}", file=sys.stderr)
            failed = True

    # 5. Gemini version stash (C5 will use this; skip if no --out or no API key)
    gemini_key = __import__("os").environ.get("GEMINI_API_KEY", "")
    if args.out and gemini_key:
        try:
            gr = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash"
                f"?key={gemini_key}",
                timeout=10,
            )
            gemini_info = gr.json() if gr.status_code == 200 else {"error": gr.status_code}
        except Exception as exc:
            gemini_info = {"error": str(exc)}
        out_dir = pathlib.Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "gemini_versions.json").write_text(
            json.dumps(gemini_info, indent=2), encoding="utf-8"
        )

    if failed:
        return 1

    print("preflight OK: all checks passed.", file=sys.stderr)
    return 0


def _dispatch_provider(
    model: str,
    photo_path: pathlib.Path,
    prompt: str,
    ollama_base_url: str = "http://localhost:11434",
) -> tuple[dict | None, dict]:
    """Route model string to the correct provider and return (parsed, metadata)."""
    if model.startswith("ollama:"):
        tag = model[len("ollama:"):]
        return _cold_call_ollama(tag, photo_path, prompt, ollama_base_url)
    if model in _KNOWN_OLLAMA_VISION_TAGS:
        return _cold_call_ollama(model, photo_path, prompt, ollama_base_url)
    if model.startswith("gemini-"):
        raise NotImplementedError("gemini lands in C5")
    if model == "llama-3.2-90b-vision-preview":
        raise NotImplementedError("groq deferred")
    raise ValueError(f"unknown provider: {model}")


def cmd_run(args: argparse.Namespace) -> int:
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    invalid = _validate_models(models)
    if invalid:
        print(
            f"unknown provider in --models: {', '.join(invalid)}. "
            f"Supported: ollama:*, gemini-*, llama-3.2-90b-vision-preview",
            file=sys.stderr,
        )
        return 1

    corpus = pathlib.Path(args.corpus)
    if not corpus.exists():
        print(f"corpus path does not exist: {corpus}", file=sys.stderr)
        return 1

    # Verify synonyms.yml parses before any provider calls.
    synonyms = _load_synonyms()
    fractions = synonyms.get("unicode_fractions", {})

    out = pathlib.Path(args.out) if args.out else (
        _RESULTS_ROOT / str(date.today())
    )
    out.mkdir(parents=True, exist_ok=True)

    pairs = _load_corpus(corpus)

    # Apply --corpus-glob filter
    if args.corpus_glob:
        import fnmatch
        pairs = [(p, g) for p, g in pairs if fnmatch.fnmatch(p.name, args.corpus_glob)]

    if not pairs:
        print("no photo+golden pairs found in corpus", file=sys.stderr)
        return 1

    # Optional resume: skip already-terminal (model, photo) pairs
    already_done: set[tuple[str, str]] = set()
    if args.resume_from:
        resume_dir = _resolve_resume_dir(args.resume_from, _RESULTS_ROOT)
        already_done = _resume_from(resume_dir)
        if resume_dir != out:
            import shutil
            existing = resume_dir / "runs.jsonl"
            if existing.exists():
                shutil.copy(existing, out / "runs.jsonl")

    prompt = _load_prompt()

    raw_dir = out / "raw"

    for model in models:
        for photo_path, golden in pairs:
            photo_basename = photo_path.name
            if (model, photo_basename) in already_done:
                print(f"skip (already done): {model} {photo_basename}", file=sys.stderr)
                continue

            started_at = datetime.now(timezone.utc).isoformat()

            # pending row
            _append_row(out, RunRow(
                model=model, photo=photo_basename, status="pending", started_at=started_at,
            ))

            # calling row
            _append_row(out, RunRow(
                model=model, photo=photo_basename, status="calling",
            ))

            try:
                parsed, metadata = _dispatch_provider(
                    model, photo_path, prompt, args.ollama_base_url,
                )
            except NotImplementedError as exc:
                ended_at = datetime.now(timezone.utc).isoformat()
                _append_row(out, RunRow(
                    model=model, photo=photo_basename, status="provider_error",
                    error=str(exc), ended_at=ended_at,
                ))
                print(f"provider_error: {model} {photo_basename}: {exc}", file=sys.stderr)
                continue
            except Exception as exc:
                ended_at = datetime.now(timezone.utc).isoformat()
                _append_row(out, RunRow(
                    model=model, photo=photo_basename, status="provider_error",
                    error=str(exc), ended_at=ended_at,
                ))
                print(f"provider_error: {model} {photo_basename}: {exc}", file=sys.stderr)
                continue

            ended_at = datetime.now(timezone.utc).isoformat()

            if parsed is None:
                raw_dir.mkdir(exist_ok=True)
                safe_model = re.sub(r"[^a-zA-Z0-9._-]", "_", model)
                raw_file = raw_dir / f"{photo_path.stem}-{safe_model}.txt"
                raw_file.write_text(metadata.get("raw_response") or "", encoding="utf-8")
                _append_row(out, RunRow(
                    model=model, photo=photo_basename, status="parse_fail",
                    latency_s=metadata.get("latency_s"),
                    cold_load_s=metadata.get("cold_load_s"),
                    error=f"parse_fail: raw at {raw_file}",
                    ended_at=ended_at,
                ))
                print(
                    f"parse_fail: {model} {photo_basename}; raw response at {raw_file}",
                    file=sys.stderr,
                )
                continue

            # parsed_ok row
            _append_row(out, RunRow(
                model=model, photo=photo_basename, status="parsed_ok",
                latency_s=metadata.get("latency_s"),
                cold_load_s=metadata.get("cold_load_s"),
                tokens_used=metadata.get("eval_count"),
                extracted=parsed,
                ended_at=ended_at,
            ))

            # scored row
            score = _score(parsed, golden, synonyms, fractions)
            _append_row(out, RunRow(
                model=model, photo=photo_basename, status="scored",
                latency_s=metadata.get("latency_s"),
                cold_load_s=metadata.get("cold_load_s"),
                tokens_used=metadata.get("eval_count"),
                extracted=parsed,
                score=score,
                ended_at=ended_at,
            ))

            f1 = score.get("ingredient_f1", 0.0)
            print(
                f"scored: {model} {photo_basename} f1={f1:.3f} "
                f"lat={metadata.get('latency_s', '?')}s cold={metadata.get('cold_load_s', '?')}s",
                file=sys.stderr,
            )

    print(f"run complete: {out / 'runs.jsonl'}", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bake_off.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pf_p = sub.add_parser("preflight", help="Check mini readiness before running the bench.")
    pf_p.add_argument(
        "--ssh-host", default="homeserver@homeserver", metavar="USER@HOST",
        help="SSH target for mini checks (default: homeserver@homeserver).",
    )
    pf_p.add_argument(
        "--models-to-check",
        default="qwen2.5vl:7b,qwen2.5vl:3b,llama3.2-vision:11b,minicpm-v:8b",
        metavar="CSV",
        help="Comma-separated Ollama tags to verify are pulled (default: all 4 vision models).",
    )
    pf_p.add_argument(
        "--out", metavar="PATH",
        help="Output directory for stash files (e.g. gemini_versions.json). Optional.",
    )

    run_p = sub.add_parser("run", help="Run the bake-off.")
    run_p.add_argument("--corpus", required=True, metavar="PATH",
                       help="Directory of recipe photos + golden.json files.")
    run_p.add_argument("--models", required=True, metavar="CSV",
                       help="Comma-separated provider strings.")
    run_p.add_argument("--gemini-max-calls", type=int, default=0, metavar="INT",
                       help="Hard cap on total Gemini API calls across this run (default 0).")
    run_p.add_argument("--resume-from", metavar="STR|latest",
                       help="Resume from a previous run; 'latest' finds the most recent out dir.")
    run_p.add_argument("--out", metavar="PATH",
                       help="Output directory (default: meal_planner/eval/results/<today>/).")
    run_p.add_argument("--corpus-glob", metavar="STR",
                       help="Glob pattern to subset the corpus (e.g. '*.png').")
    run_p.add_argument(
        "--ollama-base-url", default="http://localhost:11434", metavar="URL",
        help="Ollama API base URL (default: http://localhost:11434). "
             "Use with SSH tunnel when running from laptop.",
    )

    args = parser.parse_args()

    if args.command == "preflight":
        sys.exit(cmd_preflight(args))
    elif args.command == "run":
        sys.exit(cmd_run(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

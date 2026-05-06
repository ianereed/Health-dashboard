"""Gemini Vision fallback for the per-case outlier path. STUB — implemented in Chunk 3.

When extract_recipe_from_photo returns status='timeout', the worker posts a decision
card. If the user picks "Use Gemini", the card resolver calls this function. Returns
the same shape as call_ollama_vision: (parsed_dict_or_None, metadata).
"""
from __future__ import annotations

from pathlib import Path


def call_gemini_vision(
    photo_path: Path, *, api_key: str
) -> tuple[dict | None, dict]:
    """Call Gemini 2.5 Flash with a single photo. Returns (parsed_or_None, metadata).

    Same return shape as meal_planner.vision._ollama.call_ollama_vision so the
    card resolver can branch on the result uniformly. Implementation lands in
    Chunk 3 (alongside the cost-tracking ledger).
    """
    raise NotImplementedError("Chunk 3")

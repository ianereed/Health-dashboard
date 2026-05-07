"""Smoke test: recipe_extraction_prompt.txt must contain compound-qty guidance."""
from __future__ import annotations

from meal_planner.vision import _ollama


def test_extraction_prompt_has_compound_qty_guidance():
    """Prompt must explicitly forbid compound qty strings so the model splits them."""
    # Clear the module-level cache to ensure we read from the current file.
    _ollama._PROMPT_TEXT = None
    text = _ollama.load_prompt()
    assert "compound" in text, "prompt must contain the word 'compound'"
    assert "single" in text.lower(), (
        "prompt must instruct the model to use a single quantity per entry"
    )

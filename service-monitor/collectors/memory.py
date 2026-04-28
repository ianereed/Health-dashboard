"""Read memory-tracker state file."""
import json
from pathlib import Path

import streamlit as st

HISTORY_PATH = Path(
    "~/Library/Application Support/home-tools/memory_history.json"
).expanduser()


@st.cache_data(ttl=10)
def get_memory() -> dict:
    """Return tracker state. {} if missing/unreadable."""
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text())
    except Exception:
        return {}

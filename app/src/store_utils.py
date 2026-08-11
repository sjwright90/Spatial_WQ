"""Helpers for (de)serializing dcc.Store JSON string payloads.

Kept separate from data_process.py, which is about reshaping dataframes, not
about the Store-payload-as-JSON-string convention every callback in app.py
round-trips through.
"""

import json
from typing import Any, Optional


def load_store(raw: Optional[str]) -> Optional[dict]:
    """json.loads a dcc.Store string payload, returning None if raw is falsy.

    Centralizes the `json.loads(session)` / `json.loads(raw_upload_data)` /
    `json.loads(meta_data)` pattern repeated across app.py callbacks, along
    with each callback's own `if raw: ... else None` guard.
    """
    return json.loads(raw) if raw else None


def dump_store(data: Any) -> str:
    """json.dumps wrapper for symmetry with load_store at call sites."""
    return json.dumps(data)

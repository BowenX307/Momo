"""Built-in default personas and LLM sampling params.

These are the canonical fallbacks used whenever no runtime override is set.
The persona strings live in ``default_personas.json`` (generated once from the
original hardcoded prompts so the exact wording is preserved). ``DEFAULT_PARAMS``
mirrors the original sampling parameters from the DeepSeek payload.
"""

from __future__ import annotations

import json
from pathlib import Path

_PERSONAS_FILE = Path(__file__).parent / "default_personas.json"

DEFAULT_PERSONAS: dict[str, str] = json.loads(
    _PERSONAS_FILE.read_text(encoding="utf-8")
)

# Original sampling params (previously hardcoded in deepseek.py).
DEFAULT_PARAMS: dict = {
    "temperature": 0.72,
    "top_p": 0.9,
    "frequency_penalty": 0.4,
    "presence_penalty": 0.3,
    "max_tokens": 220,
}

# Persona keys the admin API is allowed to edit.
PERSONA_KEYS: tuple[str, ...] = tuple(DEFAULT_PERSONAS.keys())

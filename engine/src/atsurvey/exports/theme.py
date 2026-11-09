"""Report theme generated from design/tokens.json (see scripts/build_tokens.py)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache
def load_theme() -> dict:
    return json.loads(
        resources.files("atsurvey.exports").joinpath("theme.json").read_text(encoding="utf-8")
    )


def color(name: str) -> str:
    return load_theme()["color"][name]

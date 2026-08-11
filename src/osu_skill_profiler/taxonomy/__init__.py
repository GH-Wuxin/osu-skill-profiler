"""Provisional skill taxonomy (machine-readable)."""

from __future__ import annotations

import json
from pathlib import Path

TAXONOMY_FILE = Path(__file__).parent / "v0.json"


def load_taxonomy() -> dict:
    return json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))


def taxonomy_version() -> str:
    return str(load_taxonomy()["taxonomy_version"])


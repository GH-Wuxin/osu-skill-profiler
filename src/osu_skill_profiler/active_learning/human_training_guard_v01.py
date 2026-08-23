"""Fail-closed training eligibility for human response artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DISPOSITION_SCHEMA_VERSION = "0.1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def assert_training_eligible(response_path: Path, disposition_path: Path) -> dict[str, Any]:
    """Return disposition only when exact response bytes are explicitly eligible.

    Missing, mismatched and explicitly ineligible disposition all fail closed.
    """

    disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
    if disposition.get("schema_version") != DISPOSITION_SCHEMA_VERSION:
        raise ValueError("unsupported human response disposition schema")
    actual = sha256_file(response_path)
    if disposition.get("response_sha256") != actual:
        raise ValueError("human response disposition hash mismatch")
    if disposition.get("training_eligible") is not True:
        raise ValueError("human response artifact is not training eligible")
    return disposition


__all__ = ["DISPOSITION_SCHEMA_VERSION", "sha256_file", "assert_training_eligible"]

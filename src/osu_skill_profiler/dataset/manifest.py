"""Dataset manifest: metadata about .osu samples without embedding the files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from .. import SCHEMA_VERSION

MANIFEST_SCHEMA_VERSION = "0.1.0"


class ManifestError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def checksum_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _validate_sample(sample: Any, index: int) -> None:
    _require(isinstance(sample, dict), f"samples[{index}] must be an object")
    _require(isinstance(sample.get("sample_id"), str) and sample["sample_id"], f"samples[{index}].sample_id is required")
    _require(isinstance(sample.get("source"), str) and sample["source"], f"samples[{index}].source is required")
    beatmap_id = sample.get("beatmap_id")
    beatmapset_id = sample.get("beatmapset_id")
    if beatmap_id is not None:
        _require(isinstance(beatmap_id, int) and beatmap_id > 0, f"samples[{index}].beatmap_id must be a positive int or null")
    if beatmapset_id is not None:
        _require(isinstance(beatmapset_id, int) and beatmapset_id > 0, f"samples[{index}].beatmapset_id must be a positive int or null")
    _require(isinstance(sample.get("mapper"), str), f"samples[{index}].mapper is required")
    _require(isinstance(sample.get("reference"), str) and sample["reference"], f"samples[{index}].reference is required")
    checksum = sample.get("checksum")
    _require(isinstance(checksum, str) and checksum.startswith("sha256:"), f"samples[{index}].checksum must be sha256:<hex>")
    metadata = sample.get("metadata")
    _require(metadata is None or isinstance(metadata, dict), f"samples[{index}].metadata must be an object or null")


def validate_manifest(manifest: Any) -> None:
    """Validate manifest structure without touching the referenced files."""

    _require(isinstance(manifest, dict), "manifest must be an object")
    _require(manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION, "manifest.schema_version mismatch")
    _require(isinstance(manifest.get("parser_version"), str), "manifest.parser_version is required")
    _require(isinstance(manifest.get("feature_version"), str), "manifest.feature_version is required")
    _require(isinstance(manifest.get("samples"), list), "manifest.samples must be a list")
    seen_ids: set[str] = set()
    for index, sample in enumerate(manifest["samples"]):
        _validate_sample(sample, index)
        sample_id = sample["sample_id"]
        _require(sample_id not in seen_ids, f"duplicate sample_id {sample_id!r}")
        seen_ids.add(sample_id)


def load_manifest(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(raw)
    return raw


def verify_manifest_files(manifest: dict, base_dir: str | Path | None = None) -> list[str]:
    """Optionally verify that every local reference exists and matches its checksum."""

    errors: list[str] = []
    for sample in manifest["samples"]:
        reference = Path(sample["reference"])
        if not reference.is_absolute() and base_dir is not None:
            reference = Path(base_dir) / reference
        if not reference.exists():
            errors.append(f"{sample['sample_id']}: missing file {reference}")
            continue
        actual = checksum_file(reference)
        if actual != sample["checksum"]:
            errors.append(f"{sample['sample_id']}: checksum mismatch ({actual})")
    return errors


"""Canonical dataset split identities for the v0.1 evaluation boundary.

This module implements the content-addressed identities and deterministic
assignment rules that the dataset split audit tooling relies on:

- ``map_key``: the already-present SHA-256 checksum of the `.osu` file.
- ``set_group_key``: beatmapset id when trustworthy, else local set folder.
- ``mapper_group_key``: normalised exact creator name; creator ids are not
  present in the current manifest, so the best available quality is
  ``NAME_ONLY``.
- split assignment: SHA-256 over ``split_version + seed + group key`` so that
  membership is stable, machine-independent and independent of enumeration
  order.

Identical checksums (known duplicates) are always unioned into the same
assignment component so identical file content can never cross a split.

No training, no taxonomy, no labels: this layer only builds the exam.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Iterator, Sequence

SPLIT_VERSION = "0.1.0"
DEFAULT_SEED = "osu-skill-profiler-dataset-split-v01"

LEGACY_FORMAT_MAX = 5

SPLITS = ("train", "val", "test")
DEFAULT_TARGETS = (0.80, 0.10, 0.10)

CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class SplitError(ValueError):
    pass


def checksum_digest(checksum: str) -> bytes:
    """Return the raw 32-byte digest for a ``sha256:<hex>`` checksum."""

    if not isinstance(checksum, str) or not CHECKSUM_RE.fullmatch(checksum):
        raise SplitError(f"invalid checksum: {checksum!r}")
    return bytes.fromhex(checksum[len("sha256:"):])


def normalize_mapper_name(name: Any) -> str | None:
    """Normalise a creator name for exact matching only.

    ``None`` is returned for missing/empty names. No fuzzy matching, no
    transliteration, no LLM resolution.
    """

    if not isinstance(name, str):
        return None
    normalized = re.sub(r"\s+", " ", name.strip().casefold())
    return normalized or None


def set_group_key(record: dict) -> tuple[str, str]:
    """Return ``(set_group_key, policy)`` for one manifest record.

    Policy:
      ``beatmapset_id`` -> ``b:<id>`` when a positive int is present.
      ``local_set_group`` -> ``l:<folder>`` otherwise.

    The record must carry ``checksum``/``sample_id`` for error reporting.
    """

    beatmapset_id = record.get("beatmapset_id")
    if isinstance(beatmapset_id, int) and beatmapset_id > 0:
        return f"b:{beatmapset_id}", "beatmapset_id"
    local = record.get("local_set_group")
    if isinstance(local, str) and local:
        return f"l:{local}", "local_set_group"
    raise SplitError(
        f"no reliable set identity for {record.get('sample_id', '<unknown>')} "
        f"(checksum {record.get('checksum', '<none>')})"
    )


def mapper_group_key(record: dict) -> tuple[str, str]:
    """Return ``(mapper_group_key, quality)`` for one manifest record.

    Quality is ``NAME_ONLY`` for non-empty normalised creator names and
    ``UNKNOWN`` otherwise. ``VERIFIED_ID`` is intentionally never emitted:
    creator ids are not present in the current corpus manifest.
    """

    name = normalize_mapper_name(record.get("mapper") or record.get("creator"))
    if name is None:
        return "u:unknown", "UNKNOWN"
    return f"n:{name}", "NAME_ONLY"


def group_hash(version: str, seed: str, group_key: str) -> int:
    """Stable content hash used only for deterministic rank ordering."""

    material = f"{version}\n{seed}\n{group_key}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], "big")


class UnionFind:
    """Small union-find used to build hard assignment components."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        parent = self._parent.get(key)
        if parent is None:
            self._parent[key] = key
            return key
        if parent != key:
            self._parent[key] = self.find(parent)
        return self._parent[key]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def components(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for key in self._parent:
            out.setdefault(self.find(key), []).append(key)
        return out


def build_components(
    records: Sequence[dict],
    group_keys: Sequence[str],
    *,
    include_unknown_mapper: bool = True,
) -> tuple[list[dict], list[tuple[str, list[str]]]]:
    """Build hard assignment components.

    Every record is a node keyed by its canonical ``map_checksum``. Records
    sharing any of the requested group keys (or an identical checksum) are
    unioned, so the resulting components can never cross a split without
    violating the corresponding constraint.

    Returns ``(annotated_records, components)`` where ``annotated_records``
    carries ``component`` and ``group_keys`` fields.
    """

    uf = UnionFind()
    group_nodes: dict[tuple[str, str], str] = {}
    annotated: list[dict] = []

    for record in records:
        checksum = record["map_checksum"]
        uf.find(checksum)
        for key in group_keys:
            value = record.get(key)
            if value is None:
                continue
            if key == "mapper_group_key" and value == "u:unknown" and not include_unknown_mapper:
                continue
            node = group_nodes.setdefault((key, value), f"{key}::{value}")
            uf.union(checksum, node)
        annotated.append(record)

    components: list[tuple[str, list[str]]] = []
    for members in uf.components().values():
        checksum_members = sorted(m for m in members if m.startswith("sha256:"))
        if not checksum_members:
            continue
        component_id = hashlib.sha256(
            "\n".join(checksum_members).encode("utf-8")
        ).hexdigest()
        components.append((component_id, checksum_members))

    member_checksums = {c for _, members in components for c in members}
    component_of: dict[str, str] = {}
    for component_id, members in components:
        for checksum in members:
            component_of[checksum] = component_id

    for record in annotated:
        record["component"] = component_of[record["map_checksum"]]
    return annotated, components


def assign_components(
    components: Iterable[tuple[str, list[str]]],
    records_by_checksum: dict[str, dict],
    *,
    targets: Sequence[float] = DEFAULT_TARGETS,
    version: str = SPLIT_VERSION,
    seed: str = DEFAULT_SEED,
) -> dict[str, str]:
    """Assign each component to a split deterministically.

    Components are ranked by ``SHA-256(split_version + seed + component)``.
    Sorted by ``(rank, component)``, boundaries are placed on cumulative map
    counts so group integrity is preserved and proportions approximate the
    requested targets.
    """

    if abs(sum(targets) - 1.0) > 1e-9 or len(targets) != 3:
        raise SplitError("targets must be three positive proportions summing to 1")
    if any(t <= 0.0 for t in targets):
        raise SplitError("targets must all be strictly positive")

    ranked = sorted(
        ((group_hash(version, seed, component_id), component_id, members) for component_id, members in components),
        key=lambda item: (item[0], item[1]),
    )
    total_maps = sum(len(members) for _, _, members in ranked)
    if total_maps == 0:
        return {}

    train_cut = round(total_maps * targets[0])
    val_cut = round(total_maps * (targets[0] + targets[1]))

    assignments: dict[str, str] = {}
    cumulative = 0
    for _, component_id, members in ranked:
        size = len(members)
        if cumulative < train_cut:
            split = "train"
        elif cumulative < val_cut:
            split = "val"
        else:
            split = "test"
        for checksum in members:
            assignments[checksum] = split
        cumulative += size
    return assignments


def legacy_format_flags(format_version: Any) -> list[str]:
    """Defensible legacy indicators.

    Only old osu! file format generations are used. This is never called
    temporal OOD: it is a FORMAT_GENERATION_PROXY.
    """

    flags: list[str] = []
    if isinstance(format_version, int) and format_version <= LEGACY_FORMAT_MAX:
        flags.append("legacy_format")
    if format_version == 128:
        flags.append("format_v128")
    return flags


def pathological_reasons(
    record: dict,
    *,
    qa_flags: Sequence[str] | None = None,
    short_lt100: Any = None,
    short_lt1000: Any = None,
) -> list[str]:
    """Deterministic pathological challenge reasons for one record.

    Provenance comes from QA flags (never clipped) and manifest metadata
    extremes that are already documented in the corpus QA reports.
    """

    reasons: list[str] = []
    metadata = record.get("metadata") or {}
    difficulty = metadata.get("difficulty") or {}
    counts = metadata.get("counts") or {}

    for flag in qa_flags or []:
        reasons.append(f"qa_flag:{flag}")

    bpm_max = metadata.get("bpm_max") or record.get("bpm_max")
    if isinstance(bpm_max, (int, float)) and abs(float(bpm_max)) >= 1e12:
        reasons.append("bpm_extreme_finite")

    repeats_max = metadata.get("repeats_max")
    if isinstance(repeats_max, (int, float)) and float(repeats_max) >= 1000:
        reasons.append("repeats_extreme_finite")

    objects = counts.get("objects")
    sliders = counts.get("sliders")
    if (
        isinstance(objects, (int, float))
        and isinstance(sliders, (int, float))
        and float(objects) > 0
        and abs(float(sliders) - float(objects)) < 1e-9
    ):
        reasons.append("all_slider")

    if isinstance(record.get("duration_ms"), (int, float)) and float(record["duration_ms"]) < 100:
        reasons.append("duration_lt_100ms")
    elif short_lt100:
        reasons.append("qa_short_lt100ms")
    if short_lt1000:
        reasons.append("qa_short_lt1000ms")

    return sorted(set(reasons))


def reference_disagreement_entry(candidate: dict) -> dict:
    """Map one Type-B candidate row to a public-safe challenge entry."""

    checksum = candidate.get("checksum")
    if not checksum:
        raise SplitError("reference disagreement candidate missing checksum")
    path = candidate.get("path") or ""
    sample_id = path[:-4] if path.endswith(".osu") else path
    object_index = candidate.get("object_index")
    return {
        "map_checksum": checksum,
        "sample_id": sample_id,
        "object_index": object_index,
        "candidate_type": candidate.get("candidate_type"),
        "reason": candidate.get("reason"),
        "ls_extreme_signals": sorted(candidate.get("ls_extreme_signals") or []),
    }


def build_split_records(
    records: Sequence[dict],
    assignments: dict[str, str],
    *,
    benchmark: str,
) -> list[dict]:
    """Project annotated records into the public split record schema."""

    out: list[dict] = []
    for record in records:
        checksum = record["map_checksum"]
        split = assignments.get(checksum)
        if split is None:
            raise SplitError(f"{benchmark}: no assignment for {checksum}")
        row = {
            "map_checksum": checksum,
            "sample_id": record.get("sample_id"),
            "beatmap_id": record.get("beatmap_id"),
            "set_group_key": record.get("set_group_key"),
            "set_group_policy": record.get("set_group_policy"),
            "mapper_group_key": record.get("mapper_group_key"),
            "mapper_identity_quality": record.get("mapper_identity_quality"),
            "split": split,
            "benchmark": benchmark,
        }
        for flag_field in ("duplicate_class", "subset_flags", "pathological_reasons"):
            if record.get(flag_field):
                row[flag_field] = record[flag_field]
        out.append(row)
    return sorted(out, key=lambda r: (r["map_checksum"], r.get("sample_id") or ""))


def assign_benchmark(
    records: Sequence[dict],
    keys: Sequence[str],
    *,
    include_unknown_mapper: bool = True,
    seed: str = DEFAULT_SEED,
    version: str = SPLIT_VERSION,
    benchmark: str = "benchmark",
) -> list[dict]:
    """One-call convenience for tests and small synthetic benchmarks."""

    annotated, components = build_components(
        records, keys, include_unknown_mapper=include_unknown_mapper
    )
    by_checksum = {record["map_checksum"]: record for record in records}
    assignments = assign_components(
        components, by_checksum, seed=seed, version=version
    )
    return build_split_records(annotated, assignments, benchmark=benchmark)


def stream_manifest_samples(path: str) -> Iterator[dict]:
    """Stream sample records from the manifest JSON document.

    The manifest is a single JSON object whose ``samples`` array is
    line-delimited; only the first and last line are envelope.
    """

    with open(path, "r", encoding="utf-8") as handle:
        first = handle.readline()
        if not first.startswith("{"):
            raise SplitError(f"{path}: unexpected manifest envelope")
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == "]}" or stripped == "]":
                break
            if stripped.endswith(","):
                stripped = stripped[:-1]
            yield json.loads(stripped)


def source_manifest_checksum(path: str) -> str:
    """SHA-256 of the raw source manifest bytes (content identity)."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"

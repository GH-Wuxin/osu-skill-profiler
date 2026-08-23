"""Deterministic preparation contracts for the first real human pilot.

This module selects a bounded subset of the already validated Active Learning
dry-run batch.  It does not generate candidates, infer answers, or mutate the
source batch.  Human responses are written by :mod:`annotation_runner_v01`
only after an annotator explicitly submits them.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Iterable, Mapping

from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu_file
from osu_skill_profiler.signals.extractor import LocalSignalExtractor
from osu_skill_profiler.signals.path import build_slider_path
from osu_skill_profiler.signals.slider import approach_rate_preempt_ms, circle_size_scale_radius

from .contracts_v01 import (
    ANNOTATION_RESPONSE_VERSION,
    ANNOTATION_SCHEMA_VERSION,
    AnnotationResponse,
    ConfidenceBand,
    PairwiseAnswer,
    PresentationOrder,
    stable_id,
)


PILOT_SCHEMA_VERSION = "0.1.0"
PILOT_GENERATOR_VERSION = "0.1.0"
PILOT_ID = "al01-human-pilot-001"
PILOT_SEED = "osu-skill-profiler-small-human-pilot-v01"
DEFAULT_ANNOTATOR_ID = "annotator_001"
DEFAULT_SESSION_ID = "pilot_session_001"
TARGET_TASKS = 40
TARGET_MAP_TASKS = 10
TARGET_SEGMENT_TASKS = 30

CONTROL_QUOTAS = {
    "EXACT_REPEAT": {"MAP_PAIR": 1, "SEGMENT_PAIR": 1},
    "AB_INVERSION": {"SEGMENT_PAIR": 2},
    "EASY_ANCHOR": {"MAP_PAIR": 1, "SEGMENT_PAIR": 1},
    "AMBIGUOUS_CONTROL": {"MAP_PAIR": 1, "SEGMENT_PAIR": 1},
    "WITHIN_MAP_SEGMENT": {"SEGMENT_PAIR": 2},
}

FORBIDDEN_BLIND_KEYS = frozenset({
    "acquisition_score",
    "challenge_categories",
    "control_group_id",
    "control_type",
    "diagnostic_expected_canonical_sign",
    "evidence_buckets",
    "mapper_group_key",
    "sampling_groups",
    "selection_reason",
    "selection_score_components",
    "set_group_key",
    "source_task_id",
    "split",
    "weak_evidence_snapshot",
})

_AUDIO_RE = re.compile(r"(?mi)^AudioFilename\s*:\s*(.+?)\s*$")


def canonical_json(value: Any) -> str:
    """Serialize strict deterministic JSON without accepting non-finite values."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path.name}:{line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"non-object JSON at {path.name}:{line_number}")
            rows.append(row)
    return rows


def write_json(path: Path, value: Any) -> dict[str, Any]:
    payload = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"bytes": len(payload), "sha256": sha256_bytes(payload)}


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    payload = ("\n".join(canonical_json(dict(row)) for row in rows) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"bytes": len(payload), "sha256": sha256_bytes(payload)}


def _rank(*parts: str) -> str:
    return hashlib.sha256((PILOT_SEED + "\n" + "\n".join(parts)).encode("utf-8")).hexdigest()


def _blind_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_BLIND_KEYS:
                found.add(key)
            found.update(_blind_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_blind_keys(child))
    return found


def validate_blind_payloads(rows: Iterable[Mapping[str, Any]]) -> None:
    for row in rows:
        leaked = _blind_keys(dict(row))
        if leaked:
            raise ValueError(f"blind task {row.get('task_id')} leaks {sorted(leaked)}")


def _pick(
    rows: Iterable[dict[str, Any]],
    *,
    count: int,
    salt: str,
) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: (_rank(salt, str(row["task_id"])), str(row["task_id"])))
    if len(ranked) < count:
        raise ValueError(f"insufficient eligible tasks for {salt}: need {count}, have {len(ranked)}")
    return ranked[:count]


def _fill_scope(
    rows: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    *,
    scope: str,
    target: int,
) -> None:
    current = sum(row["scope"] == scope for row in selected.values())
    need = target - current
    if need < 0:
        raise ValueError(f"control/source selection exceeds {scope} target")
    pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if (
            row["scope"] == scope
            and row["control_type"] == "NONE"
            and row["task_id"] not in selected
        ):
            pools[str(row["selection_reason"])].append(row)
    for reason in pools:
        pools[reason].sort(
            key=lambda row: (_rank("fill", scope, reason, str(row["task_id"])), str(row["task_id"]))
        )
    reasons = ["CHALLENGE_AUDIT", "ABSTENTION_HEAVY", "BOUNDARY_ADJACENT", "INFORMATIVE_UNCERTAIN"]
    cursor = Counter()
    while need:
        progressed = False
        for reason in reasons:
            index = cursor[reason]
            pool = pools.get(reason, [])
            while index < len(pool) and pool[index]["task_id"] in selected:
                index += 1
            cursor[reason] = index
            if index < len(pool):
                row = pool[index]
                cursor[reason] += 1
                selected[str(row["task_id"])] = row
                need -= 1
                progressed = True
                if need == 0:
                    break
        if not progressed:
            raise ValueError(f"insufficient ordinary {scope} tasks")


def select_pilot_tasks(
    task_rows: Iterable[Mapping[str, Any]],
    blind_rows: Iterable[Mapping[str, Any]],
    eligible_task_ids: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Select and deterministically space the bounded 40-task pilot."""

    tasks = [dict(row) for row in task_rows]
    blind_by_id = {str(row["task_id"]): dict(row) for row in blind_rows}
    if len(blind_by_id) != len(tasks):
        raise ValueError("source batch and blind batch task counts differ")
    eligible = frozenset(eligible_task_ids)
    available = [row for row in tasks if row["task_id"] in eligible]
    by_id = {str(row["task_id"]): row for row in available}
    if len(by_id) != len(available):
        raise ValueError("duplicate source task identity")

    selected: dict[str, dict[str, Any]] = {}
    controls: list[dict[str, Any]] = []
    for control_type, scope_quotas in CONTROL_QUOTAS.items():
        for scope, count in scope_quotas.items():
            pool = [
                row for row in available
                if row["control_type"] == control_type and row["scope"] == scope
            ]
            chosen = _pick(pool, count=count, salt=f"control:{control_type}:{scope}")
            for row in chosen:
                selected[str(row["task_id"])] = row
                controls.append(row)

    paired_controls = [
        row for row in controls if row["control_type"] in ("EXACT_REPEAT", "AB_INVERSION")
    ]
    source_rows: list[dict[str, Any]] = []
    for control in paired_controls:
        source_id = str(control.get("source_task_id") or "")
        source = by_id.get(source_id)
        if source is None:
            raise ValueError(f"control {control['task_id']} has unavailable source {source_id}")
        if source["scope"] != control["scope"]:
            raise ValueError("control/source scope mismatch")
        selected[source_id] = source
        source_rows.append(source)

    _fill_scope(available, selected, scope="MAP_PAIR", target=TARGET_MAP_TASKS)
    _fill_scope(available, selected, scope="SEGMENT_PAIR", target=TARGET_SEGMENT_TASKS)
    if len(selected) != TARGET_TASKS:
        raise AssertionError("pilot task count mismatch")

    paired_ids = {str(row["task_id"]) for row in paired_controls}
    source_ids = {str(row["task_id"]) for row in source_rows}
    other_controls = [row for row in controls if row["task_id"] not in paired_ids]
    ordinary = [
        row for row in selected.values()
        if row["task_id"] not in paired_ids
        and row["task_id"] not in {c["task_id"] for c in other_controls}
        and row["task_id"] not in source_ids
    ]
    source_rows.sort(key=lambda row: (_rank("source-order", str(row["task_id"])), str(row["task_id"])))
    ordinary.sort(key=lambda row: (_rank("ordinary-order", str(row["task_id"])), str(row["task_id"])))
    other_controls.sort(key=lambda row: (_rank("control-order", str(row["task_id"])), str(row["task_id"])))
    paired_controls.sort(key=lambda row: (_rank("paired-control-order", str(row["task_id"])), str(row["task_id"])))

    control_slots = [8, 12, 16, 20, 24, 28, 32, 35, 37, 39]
    paired_slots = control_slots[-len(paired_controls):]
    other_slots = control_slots[:-len(paired_controls)]
    slots: list[dict[str, Any] | None] = [None] * TARGET_TASKS
    source_slots = [0, 2, 4, 6]
    for slot, row in zip(source_slots, source_rows, strict=True):
        slots[slot] = row
    for slot, row in zip(other_slots, other_controls, strict=True):
        slots[slot] = row
    for slot, row in zip(paired_slots, paired_controls, strict=True):
        slots[slot] = row
    fillers = iter(ordinary)
    for index, row in enumerate(slots):
        if row is None:
            slots[index] = next(fillers)
    try:
        next(fillers)
    except StopIteration:
        pass
    else:
        raise AssertionError("not all selected tasks fit deterministic order")

    ordered = [row for row in slots if row is not None]
    order_index = {row["task_id"]: index for index, row in enumerate(ordered)}
    for control in paired_controls:
        source_index = order_index[str(control["source_task_id"])]
        control_index = order_index[str(control["task_id"])]
        if control_index - source_index < 8:
            raise AssertionError("repeat/inversion control spacing is too small")
    if any(
        ordered[index]["control_type"] != "NONE"
        and ordered[index + 1]["control_type"] != "NONE"
        for index in range(len(ordered) - 1)
    ):
        raise AssertionError("control tasks must not be adjacent")

    ordered_blind = [blind_by_id[str(row["task_id"])] for row in ordered]
    validate_blind_payloads(ordered_blind)
    diagnostics = {
        "task_count": len(ordered),
        "by_scope": dict(sorted(Counter(row["scope"] for row in ordered).items())),
        "by_proposition": dict(sorted(Counter(row["proposition"]["key"] for row in ordered).items())),
        "by_selection_reason": dict(sorted(Counter(row["selection_reason"] for row in ordered).items())),
        "by_control_type": dict(sorted(Counter(row["control_type"] for row in ordered).items())),
        "explicit_control_count": sum(row["control_type"] != "NONE" for row in ordered),
        "explicit_control_ratio": round(sum(row["control_type"] != "NONE" for row in ordered) / len(ordered), 6),
        "repeat_inversion_minimum_spacing": min(
            order_index[row["task_id"]] - order_index[row["source_task_id"]]
            for row in paired_controls
        ),
    }
    return ordered, ordered_blind, diagnostics


@dataclass(frozen=True)
class ResolvedMap:
    checksum: str
    osu_path: Path
    audio_path: Path | None


class AssetResolver:
    """Resolve selected entities through the existing Feature QA index."""

    def __init__(self, feature_rows: Iterable[Mapping[str, Any]]) -> None:
        self._paths: dict[str, Path] = {}
        for row in feature_rows:
            checksum = row.get("checksum")
            path = row.get("path_abs")
            if isinstance(checksum, str) and isinstance(path, str):
                self._paths[checksum] = Path(path)
        self._maps: dict[str, ResolvedMap] = {}
        self._bundles: dict[str, dict[str, Any]] = {}

    def resolve_map(self, checksum: str) -> ResolvedMap:
        cached = self._maps.get(checksum)
        if cached is not None:
            return cached
        path = self._paths.get(checksum)
        if path is None or not path.is_file():
            raise ValueError(f"missing .osu asset for {checksum}")
        if sha256_file(path) != checksum:
            raise ValueError(f".osu checksum mismatch for {checksum}")
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        match = _AUDIO_RE.search(text)
        audio = path.parent / match.group(1).strip() if match else None
        if audio is not None and not audio.is_file():
            audio = None
        resolved = ResolvedMap(checksum=checksum, osu_path=path, audio_path=audio)
        self._maps[checksum] = resolved
        return resolved

    def audit_task(self, task: Mapping[str, Any], *, require_audio: bool = True) -> dict[str, Any]:
        entities: list[dict[str, Any]] = []
        available = True
        reasons: list[str] = []
        for side in ("entity_a", "entity_b"):
            entity = task[side]
            ref = entity["entity"]
            checksum = str(ref["map_checksum"])
            try:
                resolved = self.resolve_map(checksum)
                beatmap = parse_osu_file(resolved.osu_path)
            except (OSError, ValueError) as exc:
                available = False
                reasons.append(f"{side}:MAP_ASSET_UNAVAILABLE:{type(exc).__name__}")
                continue
            audio_available = resolved.audio_path is not None
            if require_audio and not audio_available:
                available = False
                reasons.append(f"{side}:AUDIO_UNAVAILABLE")
            segment_resolved = True
            if task["scope"] == "SEGMENT_PAIR":
                segments = LocalSignalExtractor().extract(beatmap)["segments"]
                index = int(ref["segment_index"])
                expected_start = float(ref["segment_start_ms"])
                expected_end = float(ref["segment_end_ms"])
                segment_resolved = any(
                    segment_index == index
                    and math.isclose(float(row["start_ms"]), expected_start, abs_tol=1e-6)
                    and math.isclose(float(row["end_ms"]), expected_end, abs_tol=1e-6)
                    for segment_index, row in enumerate(segments)
                )
                if not segment_resolved:
                    available = False
                    reasons.append(f"{side}:CANONICAL_SEGMENT_UNRESOLVED")
            entities.append({
                "display_id": entity["anonymous_display_id"],
                "audio_available": audio_available,
                "map_checksum": checksum,
                "object_count": len(beatmap.hit_objects),
                "segment_resolved": segment_resolved,
            })
        return {
            "task_id": task["task_id"],
            "available": available,
            "reasons": reasons,
            "entities": entities,
        }

    def visualization_bundle(
        self,
        *,
        display_id: str,
        entity: Mapping[str, Any],
        blind_entity: Mapping[str, Any],
    ) -> dict[str, Any]:
        cached = self._bundles.get(display_id)
        if cached is not None:
            return cached
        ref = entity["entity"]
        resolved = self.resolve_map(str(ref["map_checksum"]))
        beatmap = parse_osu_file(resolved.osu_path)
        normalized = normalize(beatmap)
        cs_raw = beatmap.difficulty.get("CircleSize")
        cs = round(float(cs_raw), 4) if isinstance(cs_raw, (int, float)) and math.isfinite(float(cs_raw)) else None
        radius_result = circle_size_scale_radius(cs)
        circle_radius_px = round(float(radius_result[1]), 4) if radius_result is not None else 32.0
        ar_raw = beatmap.difficulty.get("ApproachRate")
        ar_source = "ApproachRate"
        if not isinstance(ar_raw, (int, float)) or not math.isfinite(float(ar_raw)):
            # Legacy beatmaps without an explicit AR inherit it from OD.
            ar_raw = beatmap.difficulty.get("OverallDifficulty")
            ar_source = "OverallDifficulty"
        if not isinstance(ar_raw, (int, float)) or not math.isfinite(float(ar_raw)):
            ar_raw = 5.0
            ar_source = "default"
        ar = round(float(ar_raw), 4)
        approach_preempt_ms = approach_rate_preempt_ms(ar)
        if approach_preempt_ms is None:
            raise ValueError("resolved approach rate has no finite preempt time")
        beatmap_id_raw = beatmap.metadata.get("BeatmapID")
        beatmap_id = (
            int(beatmap_id_raw)
            if isinstance(beatmap_id_raw, int) and not isinstance(beatmap_id_raw, bool) and beatmap_id_raw > 0
            else None
        )
        objects = []
        for object_index, item in enumerate(normalized.objects):
            raw = item.raw
            slider_path: list[list[float]] = []
            if raw.object_type == "slider":
                relative_points = [(0.0, 0.0)] + [
                    (float(x) - float(raw.x), float(y) - float(raw.y))
                    for x, y in raw.slider_points
                ]
                path = build_slider_path(
                    raw.slider_curve_type,
                    relative_points,
                    raw.slider_pixel_length,
                )
                slider_path = [
                    [round(float(raw.x + x), 4), round(float(raw.y + y), 4)]
                    for x, y in path.calculated_path
                ]
            objects.append({
                "object_index": object_index,
                "x": round(float(raw.x), 4),
                "y": round(float(raw.y), 4),
                "start_ms": round(float(raw.time_ms), 4),
                "end_ms": round(float(item.canonical_end_time_ms()), 4),
                "type": raw.object_type,
                "slider_path": slider_path,
                "slider_spans": raw.slider_slides,
            })
        starts = [row["start_ms"] for row in objects]
        bundle = {
            "display_id": display_id,
            "scope": blind_entity["scope"],
            "mods": "NM",
            "beatmap_id": beatmap_id,
            "circle_size": cs,
            "circle_radius_px": circle_radius_px,
            "approach_rate": ar,
            "approach_rate_source": ar_source,
            "approach_preempt_ms": approach_preempt_ms,
            "playable_window": blind_entity["playable_window"],
            "context_window": blind_entity.get("context_window"),
            "audio_available": resolved.audio_path is not None,
            "timeline": {
                "start_ms": min(starts),
                "end_ms": max(row["end_ms"] for row in objects),
            },
            "objects": objects,
        }
        self._bundles[display_id] = bundle
        return bundle

    def audio_path(self, checksum: str) -> Path | None:
        return self.resolve_map(checksum).audio_path


def _validate_control_relationships(tasks: list[dict[str, Any]]) -> None:
    by_id = {row["task_id"]: row for row in tasks}
    pairs: dict[tuple[str, str, str], str] = {}
    for row in tasks:
        keys = sorted((row["entity_a"]["entity"], row["entity_b"]["entity"]), key=canonical_json)
        pair_key = (
            row["proposition"]["key"],
            canonical_json(keys[0]),
            canonical_json(keys[1]),
        )
        prior_id = pairs.get(pair_key)
        if prior_id is None:
            pairs[pair_key] = row["task_id"]
            continue
        if row["control_type"] not in ("EXACT_REPEAT", "AB_INVERSION"):
            raise ValueError("accidental duplicate pair in pilot")
        if row["source_task_id"] != prior_id or prior_id not in by_id:
            raise ValueError("repeat/inversion does not reference selected source")
        source = by_id[prior_id]
        if row["control_type"] == "EXACT_REPEAT" and row["presentation_order"] != source["presentation_order"]:
            raise ValueError("exact repeat changed presentation order")
        if row["control_type"] == "AB_INVERSION" and row["presentation_order"] == source["presentation_order"]:
            raise ValueError("A/B inversion did not reverse presentation order")


def prepare_pilot(
    *,
    batch_path: Path,
    blind_batch_path: Path,
    source_manifest_path: Path,
    presentation_contract_path: Path,
    feature_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Prepare immutable pilot artifacts from the validated dry-run batch."""

    tasks = read_jsonl(batch_path)
    blind = read_jsonl(blind_batch_path)
    features = read_jsonl(feature_path)
    resolver = AssetResolver(features)
    audits = [resolver.audit_task(row, require_audio=True) for row in tasks]
    eligible = {row["task_id"] for row in audits if row["available"]}
    selected, selected_blind, diagnostics = select_pilot_tasks(tasks, blind, eligible)
    selected_audits = [resolver.audit_task(row, require_audio=True) for row in selected]
    if not all(row["available"] for row in selected_audits):
        raise ValueError("selected pilot contains an operationally unavailable task")
    _validate_control_relationships(selected)

    output_dir.mkdir(parents=True, exist_ok=True)
    task_info = write_jsonl(output_dir / "pilot_tasks.jsonl", selected)
    blind_info = write_jsonl(output_dir / "blind_pilot.jsonl", selected_blind)
    asset_inventory = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "policy": "selected tasks require verified .osu, canonical segment identity, and local audio",
        "selected_tasks": selected_audits,
        "source_batch_unavailable_tasks": [row for row in audits if not row["available"]],
    }
    asset_info = write_json(output_dir / "asset_inventory.json", asset_inventory)
    presentation = json.loads(presentation_contract_path.read_text(encoding="utf-8"))
    presentation_info = write_json(output_dir / "presentation_contract.json", presentation)
    manifest = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "generator_version": PILOT_GENERATOR_VERSION,
        "pilot_id": PILOT_ID,
        "source_batch_id": selected[0]["batch_id"],
        "seed": PILOT_SEED,
        "annotator_ids": [DEFAULT_ANNOTATOR_ID],
        "task_order": [row["task_id"] for row in selected],
        "control_provenance": [
            {
                "task_id": row["task_id"],
                "control_type": row["control_type"],
                "source_task_id": row.get("source_task_id"),
                "control_group_id": row.get("control_group_id"),
            }
            for row in selected if row["control_type"] != "NONE"
        ],
        "composition": diagnostics,
        "inputs": {
            "source_batch": {"artifact": "dry_run/batch.jsonl", "sha256": sha256_file(batch_path), "bytes": batch_path.stat().st_size},
            "source_blind_batch": {"artifact": "dry_run/blind_batch.jsonl", "sha256": sha256_file(blind_batch_path), "bytes": blind_batch_path.stat().st_size},
            "source_manifest": {"artifact": "dry_run/manifest.json", "sha256": sha256_file(source_manifest_path), "bytes": source_manifest_path.stat().st_size},
            "feature_index": {"artifact": "feature_qa_v02/feature_qa_5k.jsonl", "sha256": sha256_file(feature_path), "bytes": feature_path.stat().st_size},
        },
        "outputs": {
            "pilot_tasks.jsonl": task_info,
            "blind_pilot.jsonl": blind_info,
            "asset_inventory.json": asset_info,
            "presentation_contract.json": presentation_info,
        },
        "response_contract": {
            "schema_version": ANNOTATION_SCHEMA_VERSION,
            "response_version": ANNOTATION_RESPONSE_VERSION,
            "one_explicit_response_per_task": True,
            "cannot_judge_is_abstention": True,
            "human_evidence_is_ground_truth": False,
        },
        "blindness_mechanically_validated": True,
        "historical_artifacts_mutated": False,
        "model_trained": False,
        "taxonomy_frozen": False,
    }
    manifest_info = write_json(output_dir / "pilot_manifest.json", manifest)
    return {"manifest": manifest, "manifest_file": manifest_info, "resolver": resolver}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ResponseStore:
    """Append-only, resumable storage for one explicit human session."""

    def __init__(
        self,
        *,
        path: Path,
        pilot_id: str,
        tasks: Iterable[Mapping[str, Any]],
        annotator_id: str,
        session_id: str,
    ) -> None:
        self.path = path
        self.pilot_id = pilot_id
        self.tasks = [dict(row) for row in tasks]
        self.by_id = {str(row["task_id"]): row for row in self.tasks}
        self.annotator_id = annotator_id
        self.session_id = session_id
        self._lock = threading.Lock()
        self.responses: list[dict[str, Any]] = []
        if path.exists():
            self._load_existing()

    def _load_existing(self) -> None:
        rows = read_jsonl(self.path)
        seen: set[str] = set()
        for index, row in enumerate(rows):
            task_id = str(row.get("task_id", ""))
            expected = self.tasks[index]["task_id"] if index < len(self.tasks) else None
            if task_id != expected:
                raise ValueError("existing response file does not preserve pilot task order")
            if row.get("pilot_id") != self.pilot_id:
                raise ValueError("existing response pilot identity mismatch")
            if row.get("annotator_id") != self.annotator_id or row.get("session_id") != self.session_id:
                raise ValueError("existing response annotator/session mismatch")
            if task_id in seen:
                raise ValueError("duplicate response in existing session")
            self._validate_row(row)
            seen.add(task_id)
            self.responses.append(row)

    def _validate_row(self, row: Mapping[str, Any]) -> None:
        task = self.by_id.get(str(row.get("task_id", "")))
        if task is None:
            raise ValueError("response references unknown pilot task")
        response = AnnotationResponse(
            response_id=str(row["response_id"]),
            task_id=str(row["task_id"]),
            task_version=str(row["task_version"]),
            batch_id=str(row["batch_id"]),
            annotator_id=str(row["annotator_id"]),
            session_id=str(row["session_id"]),
            answer=PairwiseAnswer(str(row["answer"])),
            presentation_order=PresentationOrder(str(row["presentation_order"])),
            response_time_ms=row.get("response_time_ms"),
            confidence_band=ConfidenceBand(str(row["confidence_band"])) if row.get("confidence_band") else None,
            reason_codes=tuple(str(value) for value in row.get("reason_codes", [])),
            provenance=dict(row.get("provenance", {})),
            schema_version=str(row["schema_version"]),
            response_version=str(row["response_version"]),
        )
        if response.task_version != task["task_version"]:
            raise ValueError("response task version mismatch")
        if response.batch_id != task["batch_id"]:
            raise ValueError("response source batch mismatch")
        if response.presentation_order.value != task["presentation_order"]:
            raise ValueError("response presentation order mismatch")
        timestamp = row.get("response_timestamp_utc")
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            raise ValueError("response timestamp is missing or invalid")

    @property
    def next_index(self) -> int:
        return len(self.responses)

    def append(
        self,
        *,
        task_id: str,
        answer: str,
        response_time_ms: int,
        confidence_band: str | None = None,
        reason_codes: Iterable[str] = (),
        note: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.next_index >= len(self.tasks):
                raise ValueError("annotation session is already complete")
            task = self.tasks[self.next_index]
            if task_id != task["task_id"]:
                raise ValueError("response must follow the immutable pilot task order")
            if any(row["task_id"] == task_id for row in self.responses):
                raise ValueError("duplicate response for task")
            if not isinstance(response_time_ms, int) or response_time_ms < 0:
                raise ValueError("response_time_ms must be a non-negative integer")
            if note is not None and len(note) > 1000:
                raise ValueError("optional note exceeds 1000 characters")
            reasons = tuple(reason_codes)
            identity = {
                "pilot_id": self.pilot_id,
                "annotator_id": self.annotator_id,
                "session_id": self.session_id,
                "task_id": task_id,
            }
            response = AnnotationResponse(
                response_id=stable_id("response-", identity),
                task_id=task_id,
                task_version=str(task["task_version"]),
                batch_id=str(task["batch_id"]),
                annotator_id=self.annotator_id,
                session_id=self.session_id,
                answer=PairwiseAnswer(answer),
                presentation_order=PresentationOrder(str(task["presentation_order"])),
                response_time_ms=response_time_ms,
                confidence_band=ConfidenceBand(confidence_band) if confidence_band else None,
                reason_codes=reasons,
                provenance={
                    "pilot_id": self.pilot_id,
                    "explicit_human_submission": True,
                    "optional_note": note,
                },
            )
            row = {
                **response.as_dict(),
                "pilot_id": self.pilot_id,
                "response_timestamp_utc": _utc_now(),
            }
            self._validate_row(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json(row) + "\n")
                handle.flush()
            self.responses.append(row)
            return row


__all__ = [
    "PILOT_SCHEMA_VERSION",
    "PILOT_GENERATOR_VERSION",
    "PILOT_ID",
    "PILOT_SEED",
    "DEFAULT_ANNOTATOR_ID",
    "DEFAULT_SESSION_ID",
    "TARGET_TASKS",
    "AssetResolver",
    "ResponseStore",
    "prepare_pilot",
    "select_pilot_tasks",
    "validate_blind_payloads",
]

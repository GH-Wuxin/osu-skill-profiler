"""Ingest player score/pp rows without turning pp into a fake skill axis.

This adapter is the broad entry point for score sources such as osu! API
exports, score pages, or replay-derived records.  Every row keeps its raw pp
and performance metadata, even when the map demand is not indexed yet.  A
row becomes input to ``player_skill_rating_v01`` only when a replay/analysis
adapter has supplied explicit per-axis outcomes and the map row carries a
unified-star demand value.

That split is intentional: pp is an observed performance quantity, while a
player Skill Rating is a multi-map, multi-time capability estimate.  The
module therefore gives universal score coverage without using total pp as an
axis ground truth.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping
import sys

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01.player_skill_rating_v01 import make_evidence_record  # noqa: E402
from map_demand_v01.mod_context_v01 import normalize_mods  # noqa: E402
from map_demand_v01.unified_star_scale_v01 import AXIS_ORDER, SCALE_ID  # noqa: E402


SCHEMA_VERSION = "player_score_evidence_v0.1"
INGESTION_ID = "player-score-pp-ingestion-v0.1"
DEFAULT_NORMALIZATION_ID = "explicit-replay-axis-outcomes-v0.1"


class ScoreEvidenceError(ValueError):
    """Raised when a score row is structurally unsafe to ingest."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any, *, label: str, nonnegative: bool = False) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ScoreEvidenceError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ScoreEvidenceError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or (nonnegative and number < 0.0):
        raise ScoreEvidenceError(f"{label} must be finite and non-negative")
    return number


def _timestamp(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    try:
        _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScoreEvidenceError("timestamp must be an ISO timestamp") from exc
    return text


def _mods(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # API exports normally use a compact token such as HDHR.  Preserve it
        # as one source token rather than guessing a parser-specific split.
        return [value.upper()] if value else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return sorted({str(item).upper() for item in value if str(item).strip()})
    raise ScoreEvidenceError("mods must be a string or list")


def _canonical_mod_context(value: Any) -> str:
    normalized = normalize_mods(value)
    effective = normalized.get("effective_mods") if isinstance(normalized, Mapping) else None
    if normalized.get("status") == "NORMALIZED" and isinstance(effective, list):
        return "".join(str(item) for item in effective) or "NM"
    text = "" if value is None else str(value).strip().upper()
    if not text or text in {"NM", "NOMOD", "NONE", "[]"}:
        return "NM"
    return "".join(ch for ch in text if ch.isalnum()) or "NM"


def _map_key(value: Any, mod_context: str) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return f"{text}|{mod_context}"


def _lookup_keys(raw: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    # Prefer content identity over BID, which can name multiple local copies.
    # ``id`` is commonly the score id and must never be used as a map key.
    for field in ("map_md5", "md5", "map_id", "beatmap_id"):
        value = _text(raw.get(field))
        if value:
            keys.append(value)
            keys.append(value.lower())
    return list(dict.fromkeys(keys))


def load_map_index(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load JSONL map rows indexed by map id, beatmap id, and osu! MD5."""

    result: dict[str, dict[str, Any]] = {}

    def put(key: str, row: Mapping[str, Any]) -> None:
        existing = result.get(key)
        if existing is None:
            result[key] = dict(row)
            return
        if str(existing.get("osu_md5")) == str(row.get("osu_md5")):
            # Duplicate copies of the same content are one map identity.
            return
        result[key] = {
            "index_status": "AMBIGUOUS",
            "mod_context": row.get("mod_context"),
            "lookup_key": key,
        }
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, Mapping):
                continue
            context = _canonical_mod_context(row.get("mod_context"))
            for key in (
                row.get("map_id"),
                row.get("osu_md5"),
                row.get("beatmap_id"),
                row.get("map_md5"),
            ):
                text = _text(key)
                if text:
                    scoped = _map_key(text, context)
                    if scoped:
                        put(scoped, row)
                        put(scoped.lower(), row)
                    if context == "NM":
                        put(text, row)
                        put(text.lower(), row)
    return result


def _resolve_map(
    raw: Mapping[str, Any],
    map_index: Mapping[str, Mapping[str, Any]] | None,
    mod_context: str,
) -> dict[str, Any] | None:
    if not map_index:
        return None
    for key in _lookup_keys(raw):
        row = map_index.get(_map_key(key, mod_context) or "")
        if row is None:
            row = map_index.get((_map_key(key, mod_context) or "").lower())
        if row is None and mod_context == "NM":
            row = map_index.get(key) or map_index.get(key.lower())
        if row is not None:
            return dict(row)
    return None


def _unified_map_demand(
    map_row: Mapping[str, Any] | None,
    mod_context: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(map_row, Mapping):
        return {}
    if map_row.get("index_status") == "AMBIGUOUS":
        return {}
    if _canonical_mod_context(map_row.get("mod_context")) != mod_context:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for axis in AXIS_ORDER:
        item = (map_row.get("axes") or {}).get(axis)
        if not isinstance(item, Mapping):
            continue
        value = item.get("unified_star_equivalent")
        status = str(item.get("unified_star_status") or "UNKNOWN").upper()
        if value is None or status not in {"ADMITTED", "CANDIDATE"}:
            continue
        result[axis] = {
            "unified_star_equivalent": value,
            "unified_star_status": status,
        }
    return result


def _raw_axis_outcomes(raw: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    value = raw.get("axis_outcomes")
    return value if isinstance(value, Mapping) else {}


def ingest_score_record(
    raw: Mapping[str, Any],
    *,
    map_index: Mapping[str, Mapping[str, Any]] | None = None,
    source: str = "score_export",
    default_timestamp: str | None = None,
) -> dict[str, Any]:
    """Normalize one score/pp row and optionally emit rating evidence.

    The function is permissive about score-source field names but strict about
    identity and numeric pp.  Missing map demand or missing axis outcomes are
    retained as usable performance evidence; they are not silently converted
    into a low skill result.
    """

    if not isinstance(raw, Mapping):
        raise ScoreEvidenceError("score row must be an object")
    player_id = _text(raw.get("player_id") or raw.get("user_id") or raw.get("username"))
    if player_id is None:
        raise ScoreEvidenceError("player_id is required")
    map_id = _text(raw.get("map_id") or raw.get("beatmap_id") or raw.get("map_md5") or raw.get("md5"))
    if map_id is None:
        raise ScoreEvidenceError("map_id, beatmap_id, or map_md5 is required")
    score_id = _text(raw.get("score_id") or raw.get("id"))
    timestamp = _timestamp(raw.get("timestamp") or raw.get("created_at") or default_timestamp)
    pp = _number(raw.get("pp"), label="pp", nonnegative=True)
    accuracy = _number(raw.get("accuracy"), label="accuracy", nonnegative=True)
    mods = _mods(raw.get("mods"))
    mod_context = _canonical_mod_context(mods)
    map_row = _resolve_map(raw, map_index, mod_context)
    map_demand = {} if "FL" in mod_context else _unified_map_demand(map_row, mod_context)
    axis_outcomes = _raw_axis_outcomes(raw)
    normalization_id = _text(raw.get("normalization_id"))
    skill_record: dict[str, Any] | None = None
    skill_status = "PERFORMANCE_ONLY"
    skill_reason = "explicit_axis_outcomes_and_unified_map_demand_required"

    if axis_outcomes and map_demand:
        missing = [axis for axis in axis_outcomes if axis not in map_demand]
        if missing:
            skill_reason = "axis_outcome_without_unified_map_demand"
        elif timestamp is None:
            skill_reason = "timestamp_required_for_multi_time_skill_evidence"
        elif normalization_id is None:
            skill_reason = "normalization_id_required_for_axis_outcomes"
        else:
            skill_record = make_evidence_record(
                player_id=player_id,
                map_id=map_id,
                timestamp=timestamp,
                source=source,
                map_demand=map_demand,
                axis_outcomes=axis_outcomes,
                score_id=score_id,
                mods=_mods(raw.get("mods")),
                mod_context=mod_context,
                normalization_id=normalization_id,
                metadata={
                    "pp": pp,
                    "accuracy": accuracy,
                    "rank": raw.get("rank"),
                    "replay_available": raw.get("replay_available"),
                    "source_score_fields": sorted(str(key) for key in raw.keys()),
                },
            )
            skill_status = "READY_FOR_SKILL_RATING"
            skill_reason = "explicit_replay_or_axis_adapter_evidence"
    elif "FL" in mod_context:
        skill_reason = "flashlight_excluded_from_current_axis_contract"
    elif not map_demand:
        skill_reason = "map_demand_not_indexed_or_not_on_unified_scale"

    map_reference = {
        "status": (
            "AMBIGUOUS" if (map_row or {}).get("index_status") == "AMBIGUOUS"
            else "RESOLVED" if map_row is not None
            else "UNRESOLVED"
        ),
        "map_id": (map_row or {}).get("map_id"),
        "osu_md5": (map_row or {}).get("osu_md5"),
        "beatmap_id": (map_row or {}).get("beatmap_id"),
        "measurement_status": (map_row or {}).get("measurement_status"),
        "calibration_id": (map_row or {}).get("calibration_id"),
        "scale_id": SCALE_ID if map_demand else None,
        "unified_axis_count": len(map_demand),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "ingestion_id": INGESTION_ID,
        "player_id": player_id,
        "score_id": score_id,
        "map_id": map_id,
        "timestamp": timestamp,
        "source": source,
        "mods": mods,
        "mod_context": mod_context,
        "pp_measurement": {
            "value": pp,
            "unit": "pp",
            "status": "OBSERVED" if pp is not None else "MISSING",
        },
        "performance": {
            "accuracy": accuracy,
            "rank": raw.get("rank"),
            "max_combo": raw.get("max_combo"),
            "statistics": copy.deepcopy(raw.get("statistics")),
            "replay_available": raw.get("replay_available"),
        },
        "map_reference": map_reference,
        "skill_evidence": {
            "status": skill_status,
            "reason": skill_reason,
            "record": skill_record,
        },
        "raw_source": copy.deepcopy(dict(raw)),
    }


def ingest_score_records(
    records: Iterable[Mapping[str, Any]],
    *,
    map_index: Mapping[str, Mapping[str, Any]] | None = None,
    source: str = "score_export",
    default_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return [
        ingest_score_record(
            record,
            map_index=map_index,
            source=source,
            default_timestamp=default_timestamp,
        )
        for record in records
    ]


def skill_evidence_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Extract only rows admissible as input to the Skill Rating estimator."""

    return [
        dict(item["skill_evidence"]["record"])
        for item in records
        if isinstance(item.get("skill_evidence"), Mapping)
        and item["skill_evidence"].get("status") == "READY_FOR_SKILL_RATING"
        and isinstance(item["skill_evidence"].get("record"), Mapping)
    ]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="score/pp JSONL")
    parser.add_argument("--output", type=Path, required=True, help="normalized JSONL")
    parser.add_argument("--map-index", type=Path)
    parser.add_argument("--source", default="score_export")
    parser.add_argument("--default-timestamp")
    args = parser.parse_args(argv)
    map_index = load_map_index(args.map_index) if args.map_index else None
    with args.input.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    output = ingest_score_records(
        rows,
        map_index=map_index,
        source=args.source,
        default_timestamp=args.default_timestamp,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in output:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "input_count": len(rows),
        "output_count": len(output),
        "pp_observed_count": sum(item["pp_measurement"]["status"] == "OBSERVED" for item in output),
        "skill_ready_count": sum(item["skill_evidence"]["status"] == "READY_FOR_SKILL_RATING" for item in output),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_NORMALIZATION_ID",
    "INGESTION_ID",
    "SCHEMA_VERSION",
    "ScoreEvidenceError",
    "ingest_score_record",
    "ingest_score_records",
    "load_map_index",
    "skill_evidence_records",
]


if __name__ == "__main__":
    raise SystemExit(main())

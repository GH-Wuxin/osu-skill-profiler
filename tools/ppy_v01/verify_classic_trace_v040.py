"""Independent verifier for bounded Lazer Classic Slider traces.

The ppy host remains the source of the observed judgement result.  This tool
does not re-run it and does not pretend that a cursor replay alone proves a
judgement.  It independently rebuilds the map's nested Slider event identity
from the .osu file, checks every emitted event's slider/phase/time, and compares
the host aggregate against the Stable .osr header.  The result is a provenance
gate for the deployable map-demand release and a reproducible holdout report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from osu_skill_profiler.parser.osu_parser import parse_osu_file
from osu_skill_profiler.signals.slider import (
    SIGNAL_VERSION,
    _build_geometry,
    circle_size_scale_radius,
)


SCHEMA_VERSION = "ppy_slider_independent_verification_v040"
_OBJECT_ID = re.compile(r"^slider:(\d+):(head|tick|repeat|tail)(?::\d+)?$")
_PHASES = ("head", "tick", "repeat", "tail")


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - osu! beatmap identity is MD5 by format.
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _phase_result_counts(trace: Mapping[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in trace.get("events", []) if isinstance(trace.get("events"), list) else []:
        if isinstance(event, Mapping):
            counts[str(event.get("Phase", event.get("phase", ""))).lower()] += 1
    return counts


def _score_counts(trace: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    stats = trace.get("score_processor_statistics")
    stats = stats if isinstance(stats, Mapping) else {}
    observed = {
        "300": int(stats.get("Great", 0) or 0),
        "100": int(stats.get("Ok", 0) or 0),
        "50": int(stats.get("Meh", 0) or 0),
        "miss": int(stats.get("Miss", 0) or 0),
    }
    replay = trace.get("replay")
    replay = replay if isinstance(replay, Mapping) else {}
    header = replay.get("header_counts")
    header = header if isinstance(header, Mapping) else {}
    expected = {
        "300": int(header.get("count_300", 0) or 0),
        "100": int(header.get("count_100", 0) or 0),
        "50": int(header.get("count_50", 0) or 0),
        "miss": int(header.get("count_miss", 0) or 0),
    }
    return observed, expected


def verify_trace(trace: Mapping[str, Any], map_path: str | Path, *, holdout_role: str = "validation") -> dict[str, Any]:
    path = Path(map_path)
    beatmap = parse_osu_file(path)
    cs = _finite(beatmap.difficulty.get("CircleSize"))
    scale_radius = circle_size_scale_radius(cs)
    radius = scale_radius[1] if scale_radius is not None else None
    sliders = [obj for obj in beatmap.hit_objects if obj.object_type == "slider"]
    expected: dict[int, dict[str, list[float]]] = {}
    geometry_unknown: list[int] = []
    if radius is not None:
        for index, obj in enumerate(sliders):
            geometry = _build_geometry(
                beatmap,
                obj,
                (float(obj.x), float(obj.y)),
                radius,
                signal_version=SIGNAL_VERSION,
            )
            if not geometry.nested:
                geometry_unknown.append(index)
            expected[index] = {
                phase: [float(item.time_ms) for item in geometry.nested if item.kind == phase]
                for phase in _PHASES
            }

    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    event_ids: list[str] = []
    object_ids: list[str] = []
    phase_counts: Counter[str] = Counter()
    invalid_events: list[dict[str, Any]] = []
    timing_errors: list[float] = []
    observed_by_slider_phase: Counter[tuple[int, str]] = Counter()
    for event_index, event in enumerate(events):
        if not isinstance(event, Mapping):
            invalid_events.append({"event_index": event_index, "reason": "event_is_not_an_object"})
            continue
        event_id = str(event.get("EventIndex", event.get("event_id", "")))
        object_id = str(event.get("ObjectId", event.get("object_id", "")))
        phase = str(event.get("Phase", event.get("phase", ""))).lower()
        event_ids.append(event_id)
        object_ids.append(object_id)
        phase_counts[phase] += 1
        match = _OBJECT_ID.match(object_id)
        if match is None:
            invalid_events.append({"event_index": event_index, "reason": "object_id_shape_invalid", "object_id": object_id})
            continue
        slider_index = int(match.group(1))
        parsed_phase = match.group(2)
        if slider_index >= len(sliders) or parsed_phase != phase:
            invalid_events.append({"event_index": event_index, "reason": "slider_or_phase_not_in_map", "object_id": object_id})
            continue
        observed_by_slider_phase[(slider_index, phase)] += 1
        actual_time = _finite(event.get("StartTime", event.get("start_time_ms")))
        expected_times = expected.get(slider_index, {}).get(phase, [])
        if actual_time is None or not expected_times:
            invalid_events.append({"event_index": event_index, "reason": "event_time_or_geometry_missing", "object_id": object_id})
            continue
        timing_errors.append(min(abs(actual_time - value) for value in expected_times))

    expected_phase_counts = Counter()
    expected_by_slider_phase: Counter[tuple[int, str]] = Counter()
    for slider_index, phases in expected.items():
        for phase, times in phases.items():
            expected_phase_counts[phase] += len(times)
            expected_by_slider_phase[(slider_index, phase)] = len(times)
    observed_phase_counts = Counter({phase: int(phase_counts.get(phase, 0)) for phase in _PHASES})
    phase_count_match = observed_phase_counts == expected_phase_counts
    per_slider_phase_count_match = observed_by_slider_phase == expected_by_slider_phase
    identity_complete = (
        not invalid_events
        and len(event_ids) == len(set(event_ids))
        and all(event_ids)
        and len(object_ids) == len(set(object_ids))
        and all(object_ids)
        and phase_count_match
        and per_slider_phase_count_match
        and (not timing_errors or max(timing_errors) <= 0.5)
        and not geometry_unknown
    )
    observed_counts, expected_counts = _score_counts(trace)
    aggregate_parity = observed_counts == expected_counts
    trace_map = trace.get("map") if isinstance(trace.get("map"), Mapping) else {}
    provenance = trace.get("provenance") if isinstance(trace.get("provenance"), Mapping) else {}
    map_md5_match = trace_map.get("md5") == _md5(path)
    semantics = str(trace.get("judgement_semantics", "")).lower()
    mods = {str(item).upper() for item in (trace.get("mods") or [])}
    classic_ok = semantics == "lazer_classic" and "CL" in mods and int(trace.get("classic_slider_objects", 0) or 0) == len(sliders)
    status = "INDEPENDENT_CLASSIC_PARITY_VERIFIED" if all((classic_ok, map_md5_match, identity_complete, aggregate_parity)) else "INDEPENDENT_VERIFICATION_FAILED"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "holdout_role": holdout_role,
        "source_trace_schema_version": trace.get("schema_version"),
        "source_kind": trace.get("source_kind"),
        "judgement_semantics": semantics,
        "mods": sorted(mods),
        "classic_semantics_verified": classic_ok,
        "map": {
            "path": str(path),
            "md5": _md5(path),
            "trace_md5": trace_map.get("md5"),
            "md5_match": map_md5_match,
            "slider_count": len(sliders),
            "trace_classic_slider_objects": int(trace.get("classic_slider_objects", 0) or 0),
        },
        "independent_geometry": {
            "signal_version": SIGNAL_VERSION,
            "expected_phase_counts": {phase: int(expected_phase_counts.get(phase, 0)) for phase in _PHASES},
            "observed_phase_counts": {phase: int(observed_phase_counts.get(phase, 0)) for phase in _PHASES},
            "phase_count_match": phase_count_match,
            "per_slider_phase_count_match": per_slider_phase_count_match,
            "max_event_time_error_ms": max(timing_errors) if timing_errors else None,
            "geometry_unavailable_sliders": geometry_unknown,
            "invalid_event_count": len(invalid_events),
            "invalid_events_sample": invalid_events[:10],
            "unique_event_ids": len(event_ids) == len(set(event_ids)) and all(event_ids),
            "unique_object_ids": len(object_ids) == len(set(object_ids)) and all(object_ids),
        },
        "aggregate_parity": {
            "observed": observed_counts,
            "stable_osr_header": expected_counts,
            "exact": aggregate_parity,
        },
        "replay_provenance": {
            "score_id_identity_status": provenance.get("score_id_identity_status"),
            "map_md5_matches_replay_header": provenance.get("map_md5_matches_replay_header"),
        },
        "formal_consequence": {
            "map_demand_axis_admission": "SEPARATE_MAP_DEMAND_GATE",
            "player_skill_score_admitted": False,
            "trace_can_be_used_as_classic_event_provenance": status.endswith("VERIFIED"),
            "admission_reason": None if status.endswith("VERIFIED") else "classic_semantics_or_independent_geometry_or_aggregate_parity_failed",
        },
        "provenance": [
            "independent_python_map_nested_object_reconstruction",
            "stable_osr_header_aggregate_comparison",
            "bounded_lazer_classic_trace_only",
            "audio_muted_by_source_harness",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify one bounded Lazer Classic Slider trace independently")
    parser.add_argument("trace", type=Path)
    parser.add_argument("map", type=Path)
    parser.add_argument("--holdout-role", default="validation")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    report = verify_trace(trace, args.map, holdout_role=args.holdout_role)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report["status"].endswith("VERIFIED") else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Golden Reference Signal Corpus (Gate B).

Independent golden expectations for the corrected Official Reference Signal
Layer.

The pinned upstream executable parity harness is BLOCKED in this environment
(.NET runtimes only, no SDK), so expectations are SOURCE_AUDITED: numeric
values are re-derived by hand from the audited upstream formulas and constants
for straight-line/equal-rhythm fixtures where every bonus term is analytically
zero or directly computable; other fixtures carry invariant expectations
(gates, monotonicity, include>=exclude, deterministic repeatability, no
NaN/Inf, geometry-blocked provenance).

Expected values are never modified to make tests green; a mismatch is
reported with a classification (IMPLEMENTATION_BUG / EXPECTED_VALUE_BUG /
UPSTREAM_SEMANTIC_DIFFERENCE / PATHOLOGICAL_UNDEFINED / NUMERIC_TOLERANCE /
UNKNOWN).  UNKNOWN is a blocker for that signal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler.parser.osu_parser import parse_osu  # noqa: E402
from osu_skill_profiler.reference.ppy.contract import (  # noqa: E402
    REFERENCE_NUMERIC_SIGNALS,
    REFERENCE_VERSION,
    UPSTREAM_COMMIT,
    UPSTREAM_DIFFICULTY_VERSION,
)
from osu_skill_profiler.reference.ppy.extractor import ReferenceSignalExtractor  # noqa: E402
from osu_skill_profiler.signals.contract import PREVIOUS_SIGNAL_VERSION  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "training" / "datasets" / "golden_reference_v02"


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _smoothstep(x: float, start: float, end: float) -> float:
    x = _clamp((x - start) / (end - start), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _smootherstep(x: float, start: float, end: float) -> float:
    x = _clamp((x - start) / (end - start), 0.0, 1.0)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)


def _reverse_lerp(x: float, start: float, end: float) -> float:
    return _clamp((x - start) / (end - start), 0.0, 1.0)


def _high_bpm_speed(ms: float) -> float:
    return 1.0 / (1.0 - 0.3 ** (ms / 1000.0))


def _high_bpm_agility(ms: float) -> float:
    return 1.0 / (1.0 - 0.2 ** (ms / 1000.0))


def _high_bpm_snap(ms: float) -> float:
    return 1.0 / (1.0 - 0.03 ** ((ms / 1000.0) ** 0.65))


def _high_bpm_reading(ms: float) -> float:
    return 1.0 / (1.0 - 0.8 ** (ms / 1000.0))


def _radius(cs: float) -> float:
    scale = (1.0 - 0.7 * ((cs - 5.0) / 5.0)) / 2.0 * 1.00041
    return 64.0 * scale


def _preempt(ar: float) -> int:
    if ar > 5.0:
        value = 1200.0 + (450.0 - 1200.0) * (ar - 5.0) / 5.0
    elif ar < 5.0:
        value = 1200.0 + (1200.0 - 1800.0) * (ar - 5.0) / 5.0
    else:
        value = 1200.0
    return int(math.floor(value))


def _hit_window(od: float) -> float:
    if od > 5.0:
        value = 50.0 + (20.0 - 50.0) * (od - 5.0) / 5.0
    elif od < 5.0:
        value = 50.0 + (50.0 - 80.0) * (od - 5.0) / 5.0
    else:
        value = 50.0
    return 2.0 * (math.floor(value) - 0.5)


def _hand_straight_values(
    *,
    cs: float,
    od: float,
    ar: float,
    dt_ms: float,
    distance_raw_px: float,
    count: int,
    reading_mode: str = "sparse_zero",
) -> dict[str, dict[int, float]]:
    """Hand-derived expected values for equal-timing straight-line circles.

    All bonus terms that depend on angle repetition, rhythm change, velocity
    change and slider travel are analytically zero for this family; the
    remaining terms follow directly from the audited upstream formulas.
    """

    radius = _radius(cs)
    scale = 50.0 / radius
    small_circle = max(1.0, 1.0 + (30.0 - radius) / 70.0)
    adjusted = max(dt_ms, 25.0)
    lazy = distance_raw_px * scale
    velocity = lazy / adjusted
    hw = _hit_window(od)

    strain_time = adjusted
    strain_time /= _clamp((strain_time / hw) / 0.93, 0.92, 1.0)
    speed_bonus = 0.0
    if 60000.0 / (strain_time * 4.0) > 200.0:
        speed_bonus = 0.75 * ((75.0 - strain_time) / 40.0) ** 2
    speed_value = (1.0 + speed_bonus) * 1000.0 / strain_time * _high_bpm_speed(adjusted)

    agility_value = min(lazy, 120.0) / 120.0 * 1000.0 / adjusted * small_circle ** 1.5 * _high_bpm_agility(adjusted)

    wide_velocity = lazy / (adjusted ** 1.45)
    snap_value = (velocity + 0.25 * min(wide_velocity, wide_velocity) * 9.67) * small_circle * _high_bpm_snap(adjusted)
    flow_value = (velocity * math.sqrt(small_circle) * 0.8) ** 1.45 * _smootherstep(lazy, 0.0, 50.0)

    reading_value = None
    if reading_mode == "sparse_zero":
        reading_value = 0.0
    elif reading_mode == "ar10_value":
        preempt = _preempt(ar)
        # Density is zero for a 3-object 500ms map; only the preempt term is
        # non-zero (AR10 => preempt 450).
        preempt_difficulty = ((500.0 - preempt + abs(preempt - 500.0)) / 2.0) ** 2.5 / 140000.0
        reading_value = preempt_difficulty * _high_bpm_reading(adjusted)

    expected: dict[str, dict[int, float]] = {
        "ref.ppy.speed": {},
        "ref.ppy.agility": {},
        "ref.ppy.snap_include_sliders": {},
        "ref.ppy.snap_exclude_sliders": {},
        "ref.ppy.flow_include_sliders": {},
        "ref.ppy.flow_exclude_sliders": {},
        "ref.ppy.rhythm": {},
        "ref.ppy.reading": {},
    }
    for i in range(1, count):
        expected["ref.ppy.speed"][i] = speed_value
        expected["ref.ppy.agility"][i] = agility_value
        expected["ref.ppy.rhythm"][i] = 1.0
        if reading_value is not None and i >= 2:
            expected["ref.ppy.reading"][i] = reading_value
        if i >= 3:
            expected["ref.ppy.snap_include_sliders"][i] = snap_value
            expected["ref.ppy.snap_exclude_sliders"][i] = snap_value
            expected["ref.ppy.flow_include_sliders"][i] = flow_value
            expected["ref.ppy.flow_exclude_sliders"][i] = flow_value
    return expected


def _map(objects: list[str], *, cs: float, od: float, ar: float, format_version: int = 14) -> str:
    lines = [f"osu file format v{format_version}", "", "[General]", "Mode:0", "", "[Difficulty]"]
    lines.append(f"HPDrainRate:5\nCircleSize:{cs}\nOverallDifficulty:{od}\nApproachRate:{ar}")
    lines.append("SliderMultiplier:1.4\nSliderTickRate:2")
    lines += ["", "[TimingPoints]", "1000,500,4,2,1,60,1,0", "", "[HitObjects]"]
    lines.extend(objects)
    return "\n".join(lines) + "\n"


def fixtures() -> dict[str, dict]:
    f: dict[str, dict] = {}

    straight_500_objects = [f"{100 + i * 100},100,{1000 + i * 500},1,0" for i in range(5)]
    f["r_straight_500_cs5"] = {
        "description": "straight-line equal-rhythm circles, CS5 OD8 AR9, 500ms",
        "map": _map(straight_500_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": _hand_straight_values(cs=5.0, od=8.0, ar=9.0, dt_ms=500.0, distance_raw_px=100.0, count=5, reading_mode="sparse_zero"),
        "invariants": ["no_nan_inf", "deterministic"],
    }

    straight_50_objects = [f"{100 + i * 48},100,{1000 + i * 50},1,0" for i in range(8)]
    f["r_straight_50_cs5"] = {
        "description": "straight-line 50ms burst, CS5 OD8 AR9",
        "map": _map(straight_50_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": _hand_straight_values(cs=5.0, od=8.0, ar=9.0, dt_ms=50.0, distance_raw_px=48.0, count=8, reading_mode="skip"),
        "invariants": ["no_nan_inf", "deterministic"],
    }

    straight_cs7_objects = [f"{100 + i * 100},100,{1000 + i * 500},1,0" for i in range(5)]
    f["r_straight_500_cs7"] = {
        "description": "straight-line equal-rhythm circles, CS7 (small-circle bonus active)",
        "map": _map(straight_cs7_objects, cs=7.0, od=8.0, ar=9.0),
        "hand": _hand_straight_values(cs=7.0, od=8.0, ar=9.0, dt_ms=500.0, distance_raw_px=100.0, count=5, reading_mode="sparse_zero"),
        "invariants": ["no_nan_inf", "deterministic"],
    }

    reading_ar10_objects = ["100,100,1000,1,0", "200,100,1500,1,0", "300,100,2000,1,0"]
    f["r_reading_ar10"] = {
        "description": "3-circle sparse map AR10 (preempt term hand-derived)",
        "map": _map(reading_ar10_objects, cs=5.0, od=8.0, ar=10.0),
        "hand": _hand_straight_values(cs=5.0, od=8.0, ar=10.0, dt_ms=500.0, distance_raw_px=100.0, count=3, reading_mode="ar10_value"),
        "invariants": ["no_nan_inf", "deterministic"],
    }

    stream_objects = [f"{64 + (i % 8) * 48},{64 + (i // 8) * 96},{1000 + i * 50},1,0" for i in range(12)]
    f["r_stream_200bpm"] = {
        "description": "grid 50ms stream, rhythm baseline 1.0",
        "map": _map(stream_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "rhythm_baseline", "reading_positive_dense"],
    }

    repeated_objects = [
        "100,100,1000,1,0",
        "300,100,1250,1,0",
        "100,100,1500,1,0",
        "300,100,1750,1,0",
        "100,100,2000,1,0",
        "300,100,2250,1,0",
        "100,100,2500,1,0",
    ]
    f["r_jumps_repeated"] = {
        "description": "repeated 200px jumps, CS5 OD8 AR9",
        "map": _map(repeated_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "repeated_jump_snap_positive"],
    }

    acute_objects = [
        "100,100,1000,1,0",
        "200,100,1500,1,0",
        "200,200,2000,1,0",
        "150,100,2500,1,0",
        "200,100,3000,1,0",
    ]
    f["r_acute"] = {
        "description": "acute-angle reversal pattern",
        "map": _map(acute_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "acute_snap_positive"],
    }

    obtuse_objects = [
        "100,100,1000,1,0",
        "200,100,1500,1,0",
        "300,200,2000,1,0",
        "200,100,2500,1,0",
        "100,100,3000,1,0",
    ]
    f["r_obtuse"] = {
        "description": "obtuse/reversal pattern",
        "map": _map(obtuse_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "flow_positive"],
    }

    slider_objects = [
        "64,64,1000,1,0",
        "192,192,1500,1,0",
        "320,64,2000,2,0,L|420:64,1,100",
        "448,320,2500,1,0",
        "256,256,3000,1,0",
    ]
    f["r_slider_transition"] = {
        "description": "circle -> slider -> circle transition",
        "map": _map(slider_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "slider_include_ge_exclude"],
    }

    repeat_slider_objects = [
        "64,64,1000,1,0",
        "192,192,1500,1,0",
        "320,64,2000,2,0,L|420:64,3,100",
        "448,320,2500,1,0",
        "256,256,3000,1,0",
    ]
    f["r_repeat_slider"] = {
        "description": "3-span repeat slider (travel-distance bonus)",
        "map": _map(repeat_slider_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "slider_include_ge_exclude"],
    }

    simultaneous_objects = [
        "64,64,1000,1,0",
        "192,192,1000,1,0",
        "320,64,2000,1,0",
        "448,320,2500,1,0",
    ]
    f["r_simultaneous"] = {
        "description": "simultaneous objects (25ms adjusted delta)",
        "map": _map(simultaneous_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic"],
    }

    old_objects = ["64,64,1000,1,0", "192,192,1500,1,0", "320,64,2000,1,0"]
    f["r_old_format_v3"] = {
        "description": "legacy format v3 map",
        "map": _map(old_objects, cs=5.0, od=8.0, ar=9.0, format_version=3),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic"],
    }

    pathological_objects = [
        "64,64,1000,1,0",
        "192,192,1500,1,0",
        "320,64,2000,2,0,L|420:64,10001,100",
        "448,320,2500,1,0",
    ]
    f["r_pathological_spans"] = {
        "description": "pathological slider span count (geometry blocked)",
        "map": _map(pathological_objects, cs=5.0, od=8.0, ar=9.0),
        "hand": {},
        "invariants": ["no_nan_inf", "deterministic", "geometry_blocked"],
    }

    return f


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _verdicts(fixture_id: str, fixture: dict) -> list[dict]:
    text = fixture["map"]
    checksum = _checksum(text)
    out = ReferenceSignalExtractor().extract(parse_osu(text=text))
    rows = out["objects"]
    records: list[dict] = []

    for index, row in enumerate(rows):
        for signal in REFERENCE_NUMERIC_SIGNALS:
            actual = row[signal]
            hand = fixture.get("hand", {}).get(signal, {}).get(index)
            if hand is None:
                continue
            expected = float(hand)
            if actual is None:
                verdict = "FAIL"
                classification = "IMPLEMENTATION_BUG"
            else:
                tolerance = max(1e-9, abs(expected) * 1e-7)
                verdict = "PASS" if abs(float(actual) - expected) <= tolerance else "FAIL"
                classification = None if verdict == "PASS" else "UNKNOWN"
            records.append(
                {
                    "sample_id": fixture_id,
                    "checksum": checksum,
                    "object_index": index,
                    "start_time_ms": row["ref.start_time_ms"],
                    "signal": signal,
                    "kind": "HAND_EXPECTED",
                    "expected": expected,
                    "actual": actual,
                    "tolerance": tolerance if hand is not None else None,
                    "verdict": verdict,
                    "classification": classification,
                    "expectation_source": "SOURCE_AUDITED",
                }
            )

    for invariant in fixture.get("invariants", []):
        record = _check_invariant(fixture_id, checksum, invariant, rows)
        records.append(record)
    return records


def _check_invariant(fixture_id: str, checksum: str, invariant: str, rows: list[dict]) -> dict:
    base = {
        "sample_id": fixture_id,
        "checksum": checksum,
        "object_index": None,
        "start_time_ms": None,
        "signal": None,
        "kind": f"INVARIANT:{invariant}",
        "expected": "invariant",
        "actual": None,
        "tolerance": None,
        "verdict": "PASS",
        "classification": None,
        "expectation_source": "SOURCE_AUDITED",
    }
    if invariant == "no_nan_inf":
        bad = [
            (r["ref.original_index"], signal, row_value)
            for r in rows
            for signal in REFERENCE_NUMERIC_SIGNALS
            if isinstance((row_value := r[signal]), float) and not math.isfinite(row_value)
        ]
        if bad:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": bad[:3]})
    elif invariant == "deterministic":
        first = json.dumps(rows, sort_keys=True)
        second = json.dumps(ReferenceSignalExtractor().extract(parse_osu(text=_fixture_text(fixture_id)))["objects"], sort_keys=True)
        if first != second:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": "nondeterministic"})
    elif invariant == "rhythm_baseline":
        bad = [
            r["ref.original_index"]
            for r in rows[1:]
            if r["ref.ppy.rhythm"] is None or abs(float(r["ref.ppy.rhythm"]) - 1.0) > 1e-9
        ]
        if bad:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": bad})
    elif invariant == "reading_positive_dense":
        values = [float(r["ref.ppy.reading"]) for r in rows[2:] if r["ref.ppy.reading"] is not None]
        if not values or max(values) <= 0.0:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": values})
    elif invariant == "repeated_jump_snap_positive":
        values = [
            float(r["ref.ppy.snap_include_sliders"])
            for r in rows[3:]
            if r["ref.ppy.snap_include_sliders"] is not None
        ]
        if not values or max(values) <= 0.0:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": values})
    elif invariant == "acute_snap_positive":
        value = rows[-1]["ref.ppy.snap_include_sliders"]
        if value is None or float(value) <= 0.0:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": value})
    elif invariant == "flow_positive":
        values = [float(r["ref.ppy.flow_include_sliders"]) for r in rows[3:] if r["ref.ppy.flow_include_sliders"] is not None]
        if not values or max(values) <= 0.0:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": values})
    elif invariant == "slider_include_ge_exclude":
        bad = []
        for r in rows[3:]:
            prev_type = rows[r["ref.original_index"] - 1]["ref.object_type"]
            if prev_type != "slider":
                # include/exclude differ for every row whose previous-object
                # distance is slider-sensitive; the guaranteed relationship
                # applies to the direct slider successor.
                continue
            inc = r["ref.ppy.snap_include_sliders"]
            exc = r["ref.ppy.snap_exclude_sliders"]
            f_inc = r["ref.ppy.flow_include_sliders"]
            f_exc = r["ref.ppy.flow_exclude_sliders"]
            for left, right, signal in ((inc, exc, "snap"), (f_inc, f_exc, "flow")):
                if left is None or right is None:
                    continue
                if float(left) + 1e-12 < float(right):
                    bad.append((r["ref.original_index"], signal, float(left), float(right)))
        if bad:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": bad})
    elif invariant == "geometry_blocked":
        slider_row = rows[2]
        circle_row = rows[3]
        ok = any(flag.startswith("slider_spans_exceeded:") for flag in slider_row["ref.provenance"])
        ok = ok and circle_row["ref.ppy.agility"] is None
        ok = ok and circle_row["ref.ppy.snap_include_sliders"] is None
        ok = ok and circle_row["ref.ppy.snap_exclude_sliders"] is not None
        if not ok:
            base.update({"verdict": "FAIL", "classification": "IMPLEMENTATION_BUG", "actual": "geometry blocked semantics missing"})
    return base


def _fixture_text(fixture_id: str) -> str:
    return fixtures()[fixture_id]["map"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "golden_reference_signals.jsonl"
    all_records: list[dict] = []
    failures: list[dict] = []
    with out_path.open("w", encoding="utf-8") as fh:
        for fixture_id, fixture in fixtures().items():
            records = _verdicts(fixture_id, fixture)
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            all_records.extend(records)
            failures.extend([r for r in records if r["verdict"] == "FAIL"])
    summary = {
        "contract_version": REFERENCE_VERSION,
        "local_signal_version": PREVIOUS_SIGNAL_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_difficulty_version": UPSTREAM_DIFFICULTY_VERSION,
        "fixture_count": len(fixtures()),
        "record_count": len(all_records),
        "pass_count": sum(1 for r in all_records if r["verdict"] == "PASS"),
        "fail_count": len(failures),
        "failures": failures,
        "upstream_parity_harness": "BLOCKED (no .NET SDK; expectations SOURCE_AUDITED)",
    }
    with (args.out_dir / "golden_reference_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

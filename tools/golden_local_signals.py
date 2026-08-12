"""Golden corrected Local Signal Corpus (Gate B).

Builds a deterministic set of synthetic .osu fixtures covering circles, jumps,
streams, sliders, repeat sliders, low/high CS and AR, BPM/SV changes,
simultaneous objects, legacy format, spinner context and Aspire-like
pathological values.  For every fixture the tool records:

  - sample_id, checksum, upstream commit, difficulty version, feature version
  - per-object independent/source-audited primitive values and tolerance policy
  - local extractor values and per-signal comparison verdict

The upstream parity harness is intentionally not a runtime dependency of the
profiler; this phase reports ``UPSTREAM_PARITY_HARNESS = BLOCKED`` and
validates with audited formula constants plus independent reference values.
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

from osu_skill_profiler.parser.osu_parser import parse_osu
from osu_skill_profiler.features.schema import FEATURE_VERSION
from osu_skill_profiler.signals.contract import (
    SIGNAL_VERSION,
    UPSTREAM_COMMIT,
    UPSTREAM_DIFFICULTY_VERSION,
)
from osu_skill_profiler.signals.extractor import LocalSignalExtractor

OUT_DIR = Path(__file__).resolve().parent.parent / "training" / "datasets" / "golden_v03"


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.6g}"


def _map(
    name: str,
    difficulty: str,
    timing: str,
    objects: list[str],
    format_version: int = 14,
) -> str:
    lines = [f"osu file format v{format_version}", "", "[General]", "Mode:0", "", "[Difficulty]"]
    lines.extend(difficulty.splitlines())
    lines += ["", "[TimingPoints]"]
    lines.extend(timing.splitlines())
    lines += ["", "[HitObjects]"]
    lines.extend(objects)
    return "\n".join(lines) + "\n"


def fixtures() -> dict[str, dict]:
    """Synthetic golden fixtures keyed by sample_id."""

    f: dict[str, dict] = {}
    f["g_circles_basic"] = {
        "description": "basic circles, CS4 AR9 OD8",
        "map": _map(
            "g_circles_basic",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            [
                "64,64,1000,1,0",
                "192,192,1500,1,0",
                "320,64,2000,1,0",
                "448,320,2500,1,0",
                "256,256,3000,1,0",
            ],
        ),
        "exact": {
            "preempt": [600, 600, 600, 600, 600],
            "fade_in": [400.0, 400.0, 400.0, 400.0, 400.0],
            "hit_window_great": [63.0, 63.0, 63.0, 63.0, 63.0],
        },
        "tolerance": 1e-6,
    }
    f["g_stream_200bpm"] = {
        "description": "16-note 50ms stream, CS5 AR9 OD8",
        "map": _map(
            "g_stream_200bpm",
            "HPDrainRate:5\nCircleSize:5\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            [
                f"{64 + (i % 8) * 48},{64 + (i // 8) * 96},{1000 + i * 50},1,0"
                for i in range(16)
            ],
        ),
        "exact": {
            # The extractor emits a row for the first hit object with no
            # previous; difficulty rows start at the second object.
            "adjusted_delta": [None] + [50.0] * 15,
            "last_object_end_delta": [None] + [50.0] * 15,
            "preempt": [600] * 16,
        },
        "tolerance": 1e-6,
    }
    f["g_slider_linear"] = {
        "description": "single linear slider, hand-computed lazy geometry",
        "map": _map(
            "g_slider_linear",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0",
            [
                "64,64,1000,2,0,L|264:64,1,200,0:0:0:0:",
                "300,300,2500,1,0",
            ],
        ),
        "exact": {
            "slider_duration": [1000.0, None],
            "slider_velocity": [0.2, None],
            "lazy_travel_time": [964.0, 0.0],
            "travel_time": [964.0, 0.0],
            "slider_tick_count": [1, None],
            "slider_nested_object_count": [3, None],
            "lazy_end_position_x": [191.10907776, None],
            "lazy_end_position_y": [64.0, None],
            # Reference values from the audited ppy/osu lazy-cursor loop
            # (CS4 radius 36.4949568, scale 1.37005231...). The previous
            # hand-computed values used the CS0 radius by mistake.
            "lazy_travel_distance": [174.1460860696237, 0.0],
            "travel_distance": [174.1460860696237, 0.0],
        },
        "tolerance": 1e-6,
    }
    f["g_slider_repeat2"] = {
        "description": "repeat slider slides=2, corrected total timing and hand-computed lazy geometry",
        "map": _map(
            "g_slider_repeat2",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,L|264:64,2,200,0:0:0:0:"],
        ),
        "exact": {
            # 200px / 0.2px/ms = 1000ms per span; 2 spans = 2000ms.
            "slider_duration": [2000.0],
            "slider_single_span_duration": [1000.0],
            "slider_total_duration": [2000.0],
            "slider_repeat_count": [1],
            "slider_span_count": [2],
            "slider_tick_count": [2],
            "slider_nested_object_count": [5],
            "lazy_travel_time": [1964.0],
            "lazy_end_position_x": [136.89092224],
            "lazy_end_position_y": [64.0],
            # Audited hand values for head/tick/repeat/tick/lazy-tail loop.
            "lazy_travel_distance": [348.1565487974492],
            # One true repeat means max(1, repeat_count^0.3) == 1.
            "travel_distance": [348.1565487974492],
        },
        "tolerance": 1e-4,
    }
    f["g_slider_repeat3"] = {
        "description": "repeat slider slides=3",
        "map": _map(
            "g_slider_repeat3",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,L|264:64,3,200,0:0:0:0:"],
        ),
        "exact": {
            "slider_duration": [3000.0],
            "slider_single_span_duration": [1000.0],
            "slider_total_duration": [3000.0],
            "slider_repeat_count": [2],
            "slider_span_count": [3],
            "slider_tick_count": [3],
            "slider_nested_object_count": [7],
            "lazy_travel_time": [2964.0],
        },
        "tolerance": 1e-6,
    }
    f["g_slider_bezier"] = {
        "description": "bezier slider",
        "map": _map(
            "g_slider_bezier",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,B|64:192|192:192|192:320,1,240,0:0:0:0:"],
        ),
        "exact": {"slider_span_count": [1]},
        "tolerance": 1e-6,
    }
    f["g_slider_perfect"] = {
        "description": "perfect-curve arc slider",
        "map": _map(
            "g_slider_perfect",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,P|384:64|224:320,1,300,0:0:0:0:"],
        ),
        "exact": {"slider_span_count": [1]},
        "tolerance": 1e-6,
    }
    f["g_slider_catmull"] = {
        "description": "catmull slider",
        "map": _map(
            "g_slider_catmull",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,C|64:192|192:192|192:320,1,240,0:0:0:0:"],
        ),
        "exact": {"slider_span_count": [1]},
        "tolerance": 1e-6,
    }
    f["g_low_cs"] = {
        "description": "low CS 0 same geometry",
        "map": _map(
            "g_low_cs",
            "HPDrainRate:5\nCircleSize:0\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,1500,1,0"],
        ),
        "exact": {
            # CS0: scale=(1-0.7*(0-5)/5)/2*1.00041=0.8503485,
            # radius=64*scale=54.422304, cs_scale=50/radius.
            "radius": [54.422304, 54.422304],
            "cs_scale": [0.918740963, 0.918740963],
        },
        "tolerance": 1e-5,
    }
    f["g_high_cs"] = {
        "description": "high CS 10 same geometry",
        "map": _map(
            "g_high_cs",
            "HPDrainRate:5\nCircleSize:10\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,1500,1,0"],
        ),
        "exact": {
            "radius": [9.603936, 9.603936],
            "cs_scale": [5.206153, 5.206153],
        },
        "tolerance": 1e-5,
    }
    f["g_low_ar"] = {
        "description": "AR0 long preempt",
        "map": _map(
            "g_low_ar",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:0\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,1500,1,0"],
        ),
        "exact": {"preempt": [1800, 1800], "fade_in": [400.0, 400.0]},
        "tolerance": 1e-6,
    }
    f["g_high_ar"] = {
        "description": "AR10 short preempt",
        "map": _map(
            "g_high_ar",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:10\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,1500,1,0"],
        ),
        "exact": {"preempt": [450, 450], "fade_in": [400.0, 400.0]},
        "tolerance": 1e-6,
    }
    f["g_bpm_change"] = {
        "description": "BPM change mid-map (120 -> 240)",
        "map": _map(
            "g_bpm_change",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0\n5000,250,4,2,1,60,1,0",
            [
                "64,64,1000,2,0,L|164:64,1,100,0:0:0:0:",
                "300,300,3000,1,0",
                "64,64,5000,2,0,L|164:64,1,100,0:0:0:0:",
            ],
        ),
        "exact": {
            "slider_duration": [357.142857, None, 178.571429],
            "slider_velocity": [0.28, None, 0.56],
        },
        "tolerance": 1e-4,
    }
    f["g_sv_change"] = {
        "description": "SV change mid-map (SV1 -> SV2)",
        "map": _map(
            "g_sv_change",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0\n2000,-50,4,2,1,60,0,0",
            [
                "64,64,1000,2,0,L|164:64,1,100,0:0:0:0:",
                "300,300,3000,1,0",
                "64,64,5000,2,0,L|164:64,1,100,0:0:0:0:",
            ],
        ),
        "exact": {
            "slider_duration": [357.142857, None, 178.571429],
            "slider_velocity": [0.28, None, 0.56],
        },
        "tolerance": 1e-4,
    }
    f["g_simultaneous"] = {
        "description": "same-time objects trigger the 25ms clamp",
        "map": _map(
            "g_simultaneous",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,1000,1,0", "320,64,1020,1,0"],
        ),
        "exact": {"adjusted_delta": [None, 25.0, 25.0]},
        "tolerance": 1e-6,
    }
    f["g_legacy_v3"] = {
        "description": "legacy v3 format",
        "map": _map(
            "g_legacy_v3",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,L|164:64,1,100,0:0:0:0:", "300,300,3000,1,0"],
            format_version=3,
        ),
        "exact": {"slider_duration": [357.142857, None]},
        "tolerance": 1e-4,
    }
    f["g_spinner_context"] = {
        "description": "spinner between circles",
        "map": _map(
            "g_spinner_context",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,2000,8,0,3000", "320,64,3200,1,0", "448,320,3400,1,0"],
        ),
        "exact": {
            # Upstream setDistances skips when BaseObject is Spinner OR
            # LastObject (the immediate previous hit object) is Spinner, so
            # the circle right after the spinner is also in spinner context.
            "spinner_context": [False, True, True, False],
            "jump_cs": [None, 0.0, 0.0],
            "angle": [None, None],
        },
        "tolerance": 1e-6,
    }
    f["g_slider_tail_follow"] = {
        "description": "circle after slider near tail (flow pattern)",
        "map": _map(
            "g_slider_tail_follow",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1\nSliderTickRate:1",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,2,0,L|264:64,1,200,0:0:0:0:", "280,64,1900,1,0"],
        ),
        "exact": {
            "minimum_jump_time": [None, 25.0],
            "slider_duration": [1000.0, None],
        },
        "tolerance": 1e-6,
    }
    f["g_aspire_like"] = {
        "description": "Aspire-like absurd finite values keep provenance",
        "map": _map(
            "g_aspire_like",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1e3\nSliderTickRate:2",
            "1000,1e6,4,2,1,60,1,0",
            ["64,64,1000,2,0,L|1e300:1e300,1,1e306,0:0:0:0:", "1e299,1e299,5000,1,0"],
        ),
        "exact": {},
        "tolerance": 1e-6,
    }
    f["g_out_of_order"] = {
        "description": "file order differs from time order",
        "map": _map(
            "g_out_of_order",
            "HPDrainRate:5\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\nSliderMultiplier:1.4\nSliderTickRate:2",
            "1000,500,4,2,1,60,1,0",
            ["64,64,1000,1,0", "192,192,50000,1,0", "128,128,2000,1,0"],
        ),
        "exact": {"time_sorted_index": [0, 2, 1]},
        "tolerance": 1e-6,
    }
    return f


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pick(rows: list[dict], index: int, key: str):
    return rows[index].get(key)


def _verify_fixture(sample_id: str, fixture: dict) -> dict:
    beatmap = parse_osu(fixture["map"])
    out = LocalSignalExtractor().extract(beatmap)
    rows = out["objects"]
    exact = fixture["exact"]
    tolerance = fixture["tolerance"]
    mismatches: list[dict] = []
    matches = 0
    if out["object_count"] != len(beatmap.hit_objects):
        mismatches.append(
            {
                "sample_id": sample_id,
                "signal": "object_count",
                "expected": len(beatmap.hit_objects),
                "actual": out["object_count"],
            }
        )
    for row in rows:
        for key, value in row.items():
            if isinstance(value, float) and not math.isfinite(value):
                mismatches.append(
                    {
                        "sample_id": sample_id,
                        "signal": key,
                        "expected": "finite",
                        "actual": value,
                    }
                )
    key_map = {
        "adjusted_delta": "ls.adjusted_delta_time_ms",
        "last_object_end_delta": "ls.last_object_end_delta_time_ms",
        "jump_cs": "ls.jump_distance_cs_normalised",
        "angle": "ls.slider_aware_angle_rad",
        "spinner_context": "ls.spinner_context",
        "preempt": "ls.preempt_ms",
        "fade_in": "ls.fade_in_ms",
        "hit_window_great": "ls.hit_window_great_ms",
        "radius": "ls.radius_px",
        "cs_scale": "ls.cs_scale",
        "slider_duration": "ls.slider_duration_ms",
        "slider_single_span_duration": "ls.slider_single_span_duration_ms",
        "slider_total_duration": "ls.slider_total_duration_ms",
        "slider_repeat_count": "ls.slider_repeat_count",
        "slider_velocity": "ls.slider_velocity_px_per_ms",
        "lazy_travel_time": "ls.lazy_travel_time_ms",
        "travel_time": "ls.travel_time_ms",
        "slider_tick_count": "ls.slider_tick_count",
        "slider_nested_object_count": "ls.slider_nested_object_count",
        "slider_span_count": "ls.slider_span_count",
        "lazy_end_position_x": "ls.lazy_end_position_x_px",
        "lazy_end_position_y": "ls.lazy_end_position_y_px",
        "lazy_travel_distance": "ls.lazy_travel_distance_cs_normalised",
        "travel_distance": "ls.travel_distance_cs_normalised",
        "minimum_jump_time": "ls.minimum_jump_time_ms",
        "time_sorted_index": "ls.time_sorted_index",
        "object_count": "ls.original_index",
    }
    for expected_key, expected_values in exact.items():
        signal_key = key_map[expected_key]
        for obj_index, expected in enumerate(expected_values):
            actual = _pick(rows, obj_index, signal_key)
            ok: bool
            if expected is None:
                ok = actual is None
            elif isinstance(expected, bool):
                ok = bool(actual) == expected
            elif isinstance(expected, int) and not isinstance(expected, bool):
                ok = isinstance(actual, (int, float)) and abs(float(actual) - float(expected)) <= max(1e-9, tolerance * abs(expected))
            elif isinstance(expected, float):
                ok = isinstance(actual, (int, float)) and abs(float(actual) - expected) <= max(1e-9, tolerance * abs(expected))
            else:
                ok = actual == expected
            if ok:
                matches += 1
            else:
                mismatches.append(
                    {
                        "sample_id": sample_id,
                        "object_index": obj_index,
                        "expected_key": expected_key,
                        "signal": signal_key,
                        "expected": expected,
                        "actual": actual,
                        "tolerance": tolerance,
                    }
                )
    return {
        "sample_id": sample_id,
        "description": fixture["description"],
        "checksum": _checksum(fixture["map"]),
        "upstream_repository": "ppy/osu",
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_difficulty_version": UPSTREAM_DIFFICULTY_VERSION,
        "feature_version": FEATURE_VERSION,
        "signal_version": SIGNAL_VERSION,
        "expectation_source": "SOURCE_AUDITED",
        "tolerance": tolerance,
        "object_count": len(rows),
        "expected_checks": sum(len(v) for v in exact.values()),
        "matches": matches,
        "mismatches": mismatches,
        "pass": not mismatches,
        "local_objects": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    reports = [_verify_fixture(sample_id, fixture) for sample_id, fixture in fixtures().items()]
    corpus = {
        "schema_version": SIGNAL_VERSION,
        "feature_version": FEATURE_VERSION,
        "signal_version": SIGNAL_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_difficulty_version": UPSTREAM_DIFFICULTY_VERSION,
        "upstream_parity_harness": "BLOCKED",
        "parity_harness_reason": (
            "No isolated pinned .NET/osu! reference harness is available in "
            "this environment; validation uses audited formula constants and "
            "independent synthetic fixtures. See docs/PPY_PARITY_REPORT_V02.md."
        ),
        "samples": reports,
    }
    (args.out_dir / "golden_corpus.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    fixture_dir = args.out_dir / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for sample_id, fixture in fixtures().items():
        (fixture_dir / f"{sample_id}.osu").write_text(fixture["map"], encoding="utf-8")

    total_checks = sum(r["expected_checks"] for r in reports)
    total_matches = sum(r["matches"] for r in reports)
    failures = [r for r in reports if not r["pass"]]
    print(f"golden fixtures: {len(reports)}")
    print(f"expected checks: {total_checks}  matched: {total_matches}")
    print(f"failures: {len(failures)}")
    for report in failures:
        print(f"  FAIL {report['sample_id']}: {len(report['mismatches'])} mismatches")
        for mismatch in report["mismatches"][:5]:
            print(f"    obj {mismatch['object_index']} {mismatch['signal']}: expected={mismatch['expected']!r} actual={mismatch['actual']!r}")
    print(f"written: {args.out_dir / 'golden_corpus.json'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

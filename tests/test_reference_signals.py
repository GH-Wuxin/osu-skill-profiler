"""Gate A — unit/synthetic tests for Official Reference Signal Layer v0.1.

Covers the required synthetic matrix: snap spacing/angle sensitivity, agility
movement/time behaviour, flow movement, speed timing changes, rhythm ratio
changes, reading/preempt changes, slider transitions, same-time/25ms timing,
single-object edge cases, missing AR, pathological finite geometry,
geometry-blocked values, deterministic repeatability and object alignment.

These tests validate the independent Python reimplementation against the
audited ppy/osu semantics (pinned commit b45c1a26, difficulty version
20260706).  They are NOT executable upstream parity.
"""

from __future__ import annotations

import json
import math
import unittest

from osu_skill_profiler.parser.osu_parser import parse_osu
from osu_skill_profiler.reference.ppy.contract import (
    REFERENCE_NUMERIC_SIGNALS,
    REFERENCE_SCHEMA,
)
from osu_skill_profiler.reference.ppy.extractor import ReferenceSignalExtractor, reference_rows
from osu_skill_profiler.reference.ppy.preprocess import build_ref_objects
from osu_skill_profiler.signals.extractor import LocalSignalExtractor


def _map(
    objects: list[str],
    *,
    cs: float = 5.0,
    od: float = 8.0,
    ar: float = 9.0,
    slider_multiplier: float = 1.4,
    tick_rate: float = 2.0,
    timing: str = "1000,500,4,2,1,60,1,0",
    format_version: int = 14,
) -> str:
    lines = [f"osu file format v{format_version}", "", "[General]", "Mode:0", "", "[Difficulty]"]
    lines.append(f"HPDrainRate:5\nCircleSize:{cs}\nOverallDifficulty:{od}\nApproachRate:{ar}")
    lines.append(f"SliderMultiplier:{slider_multiplier}\nSliderTickRate:{tick_rate}")
    lines += ["", "[TimingPoints]", timing, "", "[HitObjects]"]
    lines.extend(objects)
    return "\n".join(lines) + "\n"


def _rows(beatmap_text: str) -> list[dict]:
    return ReferenceSignalExtractor().extract(parse_osu(text=beatmap_text))["objects"]


class ReferenceStructureTests(unittest.TestCase):
    def test_schema_keys_and_alignment(self) -> None:
        text = _map(
            [
                "64,64,1000,1,0",
                "192,192,1500,1,0",
                "320,64,2000,1,0",
                "448,320,2500,1,0",
                "256,256,3000,1,0",
            ]
        )
        rows = _rows(text)
        self.assertEqual(len(rows), 5)
        expected_keys = set(REFERENCE_SCHEMA)
        for index, row in enumerate(rows):
            self.assertEqual(set(row), expected_keys)
            self.assertEqual(row["ref.original_index"], index)
            self.assertIsInstance(row["ref.time_sorted_index"], int)
            self.assertIsInstance(row["ref.start_time_ms"], float)
            self.assertIn(row["ref.object_type"], ("circle", "slider", "spinner"))

    def test_first_raw_object_has_no_difficulty_row(self) -> None:
        rows = _rows(_map(["64,64,1000,1,0", "192,192,1500,1,0"]))
        self.assertEqual(rows[0]["ref.original_index"], 0)
        self.assertIn("no_difficulty_row", rows[0]["ref.provenance"])
        for signal in REFERENCE_NUMERIC_SIGNALS:
            self.assertIsNone(rows[0][signal])

    def test_single_object_map(self) -> None:
        rows = _rows(_map(["64,64,1000,1,0"]))
        self.assertEqual(len(rows), 1)
        for signal in REFERENCE_NUMERIC_SIGNALS:
            self.assertIsNone(rows[0][signal])

    def test_deterministic_repeatability(self) -> None:
        text = _map(
            [
                "64,64,1000,1,0",
                "192,192,1500,1,0",
                "320,64,2000,1,0",
                "448,320,2500,1,0",
                "256,256,3000,1,0",
            ]
        )
        first = json.dumps(_rows(text), sort_keys=True)
        second = json.dumps(_rows(text), sort_keys=True)
        self.assertEqual(first, second)

    def test_local_signal_rows_unchanged_by_geometry_hook(self) -> None:
        beatmap = parse_osu(
            text=_map(
                [
                    "64,64,1000,2,0,L|164:64,1,100",
                    "192,192,1500,1,0",
                    "320,64,2000,1,0",
                ]
            )
        )
        extractor = LocalSignalExtractor()
        plain = extractor._extract_rows(beatmap)
        hooked: list = []
        hooked_rows = extractor._extract_rows(beatmap, _geometries_out=hooked)
        self.assertEqual(plain, hooked_rows)
        self.assertEqual(len(hooked), len(plain))

    def test_no_nan_or_inf_on_finite_inputs(self) -> None:
        texts = [
            _map(["64,64,1000,1,0", "192,192,1500,1,0", "320,64,2000,1,0", "448,320,2500,1,0"]),
            _map(
                [
                    "64,64,1000,2,0,L|164:64,1,100",
                    "192,192,1500,2,0,L|292:192,2,200",
                    "320,64,2000,1,0",
                ]
            ),
            _map(["64,64,1000,1,0", "64,64,1000,1,0", "320,64,2000,1,0", "448,320,2500,1,0"]),
        ]
        for text in texts:
            for row in _rows(text):
                for signal in REFERENCE_NUMERIC_SIGNALS:
                    value = row[signal]
                    if value is not None:
                        self.assertTrue(math.isfinite(float(value)), f"{signal} non-finite: {value}")


class ReferenceEvaluatorTests(unittest.TestCase):
    def _first_computable(self, rows: list[dict], signal: str) -> float:
        values = [
            float(row[signal])
            for row in rows
            if row[signal] is not None and float(row[signal]) != 0.0
        ]
        if not values:
            self.fail(f"{signal} has no non-zero computed value")
        return max(values)

    def test_snap_spacing_increase(self) -> None:
        small = _rows(
            _map(
                [
                    "100,100,1000,1,0",
                    "200,100,1500,1,0",
                    "150,100,2000,1,0",
                    "250,100,2500,1,0",
                ]
            )
        )
        large = _rows(
            _map(
                [
                    "100,100,1000,1,0",
                    "200,100,1500,1,0",
                    "150,100,2000,1,0",
                    "450,100,2500,1,0",
                ]
            )
        )
        small_snap = self._first_computable(small, "ref.ppy.snap_include_sliders")
        large_snap = self._first_computable(large, "ref.ppy.snap_include_sliders")
        self.assertGreater(large_snap, small_snap)

    def test_angle_sensitivity(self) -> None:
        straight = _rows(
            _map(
                [
                    "100,100,1000,1,0",
                    "200,100,1500,1,0",
                    "300,100,2000,1,0",
                    "400,100,2500,1,0",
                ]
            )
        )
        acute = _rows(
            _map(
                [
                    "100,100,1000,1,0",
                    "200,100,1500,1,0",
                    "200,200,2000,1,0",
                    "150,100,2500,1,0",
                ]
            )
        )
        straight_snap = self._first_computable(straight, "ref.ppy.snap_include_sliders")
        acute_snap = self._first_computable(acute, "ref.ppy.snap_include_sliders")
        self.assertGreater(acute_snap, straight_snap)

    def test_agility_movement_and_time_behaviour(self) -> None:
        fast = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,1500,1,0",
                    "320,64,2000,1,0",
                    "448,320,2500,1,0",
                ]
            )
        )
        slow = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,2000,1,0",
                    "320,64,3000,1,0",
                    "448,320,4000,1,0",
                ]
            )
        )
        fast_value = self._first_computable(fast, "ref.ppy.agility")
        slow_value = self._first_computable(slow, "ref.ppy.agility")
        self.assertGreater(fast_value, slow_value)
        self.assertAlmostEqual(fast_value / slow_value, 2.894427190999916, places=4)

    def test_flow_movement(self) -> None:
        rows = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,1500,1,0",
                    "320,64,2000,1,0",
                    "448,320,2500,1,0",
                    "256,256,3000,1,0",
                ]
            )
        )
        flow = self._first_computable(rows, "ref.ppy.flow_include_sliders")
        self.assertGreater(flow, 0.0)

    def test_speed_timing_changes(self) -> None:
        slow = _rows(_map(["64,64,1000,1,0", "192,192,1500,1,0", "320,64,2000,1,0"]))
        fast = _rows(_map(["64,64,1000,1,0", "192,192,1250,1,0", "320,64,1500,1,0"]))
        slow_speed = self._first_computable(slow, "ref.ppy.speed")
        fast_speed = self._first_computable(fast, "ref.ppy.speed")
        self.assertGreater(fast_speed, slow_speed)

    def test_rhythm_constant_stream_is_baseline(self) -> None:
        rows = _rows(
            _map([f"{64 + (i % 8) * 48},{64 + (i // 8) * 96},{1000 + i * 50},1,0" for i in range(12)])
        )
        for row in rows[1:]:
            self.assertAlmostEqual(row["ref.ppy.rhythm"], 1.0, places=9)

    def test_rhythm_ratio_change_increases_difficulty(self) -> None:
        rows = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,1500,1,0",
                    "320,64,2000,1,0",
                    "448,320,2250,1,0",
                    "256,256,2500,1,0",
                    "128,64,3000,1,0",
                    "64,192,3250,1,0",
                    "448,192,3500,1,0",
                ]
            )
        )
        max_rhythm = max(float(row["ref.ppy.rhythm"]) for row in rows[1:])
        self.assertGreater(max_rhythm, 1.0)

    def test_reading_preempt_change(self) -> None:
        ar9 = _rows(
            _map(
                [f"{64 + (i % 8) * 48},{64 + (i // 8) * 96},{1000 + i * 50},1,0" for i in range(12)],
                ar=9.0,
            )
        )
        ar10 = _rows(
            _map(
                [f"{64 + (i % 8) * 48},{64 + (i // 8) * 96},{1000 + i * 50},1,0" for i in range(12)],
                ar=10.0,
            )
        )
        reading9 = self._first_computable(ar9, "ref.ppy.reading")
        reading10 = self._first_computable(ar10, "ref.ppy.reading")
        self.assertGreater(reading10, reading9)

    def test_slider_transition_include_extends_velocity(self) -> None:
        rows = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,1500,1,0",
                    "320,64,2000,2,0,L|420:64,1,100",
                    "448,320,2500,1,0",
                ]
            )
        )
        circle = rows[3]
        self.assertEqual(circle["ref.object_type"], "circle")
        include = float(circle["ref.ppy.snap_include_sliders"])
        exclude = float(circle["ref.ppy.snap_exclude_sliders"])
        self.assertGreaterEqual(include, exclude)
        flow_include = float(circle["ref.ppy.flow_include_sliders"])
        flow_exclude = float(circle["ref.ppy.flow_exclude_sliders"])
        self.assertGreaterEqual(flow_include, flow_exclude)

    def test_same_time_uses_25ms_adjusted_delta(self) -> None:
        rows = _rows(_map(["64,64,1000,1,0", "192,192,1000,1,0", "320,64,2000,1,0", "448,320,2500,1,0"]))
        speed_value = float(rows[1]["ref.ppy.speed"])
        self.assertGreater(speed_value, 0.0)
        self.assertTrue(math.isfinite(speed_value))
        self.assertEqual(rows[1]["ref.ppy.rhythm"], 1.0)

    def test_missing_ar_produces_unavailable_reading(self) -> None:
        text = _map(
            ["64,64,1000,1,0", "192,192,1500,1,0", "320,64,2000,1,0", "448,320,2500,1,0"],
            ar=None,  # type: ignore[arg-type]
        )
        text = text.replace("ApproachRate:None\n", "")
        rows = _rows(text)
        self.assertIn("ar_missing", rows[2]["ref.provenance"])
        self.assertIsNone(rows[2]["ref.ppy.reading"])
        self.assertIn("ref_unavailable:ref.ppy.reading", rows[2]["ref.provenance"])
        self.assertEqual(rows[1]["ref.ppy.reading"], 0.0)

    def test_spans_exceeded_blocks_geometry_dependent_signals(self) -> None:
        rows = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,1500,1,0",
                    "320,64,2000,2,0,L|420:64,10001,100",
                    "448,320,2500,1,0",
                ]
            )
        )
        slider = rows[2]
        self.assertIn("slider_spans_exceeded:10001", slider["ref.provenance"])
        self.assertTrue(slider["ref.provenance"])
        circle = rows[3]
        # Agility needs the previous slider's lazy travel distance.
        self.assertIsNone(circle["ref.ppy.agility"])
        # Snap include needs previous lazy travel; exclude does not.
        self.assertIsNone(circle["ref.ppy.snap_include_sliders"])
        self.assertIsNotNone(circle["ref.ppy.snap_exclude_sliders"])

    def test_gate_zero_semantics(self) -> None:
        rows = _rows(
            _map(
                [
                    "64,64,1000,1,0",
                    "192,192,1500,1,0",
                    "320,64,2000,1,0",
                    "448,320,2500,1,0",
                ]
            )
        )
        self.assertEqual(rows[1]["ref.ppy.snap_include_sliders"], 0.0)
        self.assertEqual(rows[1]["ref.ppy.flow_include_sliders"], 0.0)
        self.assertEqual(rows[1]["ref.ppy.reading"], 0.0)
        self.assertGreater(rows[1]["ref.ppy.speed"], 0.0)


if __name__ == "__main__":
    unittest.main()

"""Gate A - unit/synthetic tests for Local Signal Layer v0.2.

Covers the 25ms timing clamps, CS scaling, circle jumps, sliders, repeat
sliders, lazy end, slider-aware angles, preempt, double-tap feasibility,
pathological finite values, missing AR, old formats, ordering provenance,
segment aggregation, determinism and a complexity regression.
"""

import math
import time
import unittest

from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu, parse_osu_file
from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.signals.contract import (
    DUPLICATE_ALIASES,
    LEGACY_SIGNAL_VERSION,
    SIGNAL_SCHEMA_V02,
    migration_table,
)
from osu_skill_profiler.signals.extractor import LocalSignalExtractor, segment_local_signals
from osu_skill_profiler.signals.slider import (
    approach_rate_preempt_ms,
    circle_size_scale_radius,
    overall_difficulty_great_window_ms,
)

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def _extract(text: str) -> dict:
    # This file is the historical Local Signal v0.2 regression suite. New
    # corrected semantics live in test_foundation_remediation_v01.py.
    return LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(parse_osu(text))


def _object(text: str, index: int) -> dict:
    return _extract(text)["objects"][index]


class TimingTests(unittest.TestCase):
    def test_25ms_delta_clamp_and_same_time(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "64,64,1000,1,0\n"
            "64,64,1020,1,0\n"
        )
        rows = _extract(text)["objects"]
        self.assertEqual(rows[1]["ls.delta_time_ms"], 0.0)
        self.assertEqual(rows[1]["ls.adjusted_delta_time_ms"], 25.0)
        self.assertEqual(rows[1]["ls.last_object_end_delta_time_ms"], 25.0)
        self.assertEqual(rows[2]["ls.delta_time_ms"], 20.0)
        self.assertEqual(rows[2]["ls.adjusted_delta_time_ms"], 25.0)
        self.assertEqual(rows[2]["ls.last_object_end_delta_time_ms"], 25.0)

    def test_first_object_has_no_timing_signals(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "64,64,1500,1,0\n"
        )
        row = _object(text, 0)
        self.assertIsNone(row["ls.delta_time_ms"])
        self.assertIsNone(row["ls.adjusted_delta_time_ms"])
        self.assertIsNone(row["ls.last_object_end_delta_time_ms"])
        self.assertIn("no_previous", row["ls.provenance"])

    def test_last_object_end_delta_is_adjusted_for_first_row(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "64,64,1500,1,0\n"
        )
        row = _object(text, 1)
        self.assertEqual(row["ls.last_object_end_delta_time_ms"], 500.0)

    def test_last_object_end_delta_uses_previous_end(self):
        # Previous object is a 1000ms slider ending at 2500; next starts at 2400.
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "64,64,1500,2,0,L|264:64,1,200,0:0:0:0:\n"
            "300,300,2400,1,0\n"
        )
        row = _object(text, 2)
        self.assertEqual(row["ls.last_object_end_delta_time_ms"], 25.0)
        # Row 1 is the first difficulty row: uses adjusted delta, not end delta.
        self.assertEqual(_object(text, 1)["ls.last_object_end_delta_time_ms"], 500.0)


class SpatialTests(unittest.TestCase):
    def test_jump_distance_raw_and_cs(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "192,192,1500,1,0\n"
        )
        row = _object(text, 1)
        self.assertAlmostEqual(row["ls.jump_distance_raw_px"], math.hypot(128, 128), places=6)
        radius = circle_size_scale_radius(4.0)[1]
        self.assertAlmostEqual(row["ls.jump_distance_cs_normalised"], math.hypot(128, 128) * 50 / radius, places=6)
        self.assertEqual(row["ls.minimum_jump_distance_cs_normalised"], row["ls.lazy_jump_distance_cs_normalised"])

    def test_low_vs_high_cs_same_geometry(self):
        def jump(cs: float) -> float:
            text = (
                "osu file format v14\n"
                f"[Difficulty]\nCircleSize:{cs}\n"
                "[HitObjects]\n"
                "64,64,1000,1,0\n"
                "192,192,1500,1,0\n"
            )
            return _object(text, 1)["ls.jump_distance_cs_normalised"]

        low = jump(0.0)
        high = jump(10.0)
        self.assertGreater(high, low)
        radius0 = circle_size_scale_radius(0.0)[1]
        radius10 = circle_size_scale_radius(10.0)[1]
        self.assertAlmostEqual(high / low, radius0 / radius10, places=6)

    def test_spinner_context_zeroes_jump_distances(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,8,0,2000\n"
            "192,192,2100,1,0\n"
            "64,64,2200,1,0\n"
        )
        rows = _extract(text)["objects"]
        self.assertTrue(rows[1]["ls.spinner_context"])
        self.assertEqual(rows[1]["ls.jump_distance_cs_normalised"], 0.0)
        self.assertEqual(rows[1]["ls.lazy_jump_distance_cs_normalised"], 0.0)
        self.assertEqual(rows[1]["ls.minimum_jump_distance_cs_normalised"], 0.0)
        self.assertIsNone(rows[1]["ls.slider_aware_angle_rad"])
        self.assertIn("previous_is_spinner", rows[1]["ls.provenance"])
        # Row 2's previous is a circle: distances are real again.
        self.assertFalse(rows[2]["ls.spinner_context"])
        self.assertGreater(rows[2]["ls.jump_distance_cs_normalised"], 0.0)


class SliderTests(unittest.TestCase):
    def test_linear_slider_lazy_end(self):
        # CS=4 => radius=36.49496, scale=1.370052; SM=1, BPM=120 => v=0.2 px/ms.
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,2,0,L|264:64,1,200,0:0:0:0:\n"
            "300,300,2500,1,0\n"
        )
        row = _object(text, 0)
        self.assertAlmostEqual(row["ls.slider_duration_ms"], 1000.0, places=6)
        self.assertAlmostEqual(row["ls.slider_velocity_px_per_ms"], 0.2, places=6)
        self.assertAlmostEqual(row["ls.lazy_travel_time_ms"], 964.0, places=6)
        self.assertEqual(row["ls.slider_tick_count"], 1)
        self.assertEqual(row["ls.slider_nested_object_count"], 3)
        # Hand-computed lazy cursor path for [head(100,0), tick(100,0), tail(200,0)].
        radius = circle_size_scale_radius(4.0)[1]
        scale = 50.0 / radius
        cursor = 0.0
        lazy_distance = 0.0
        tick_move = 100.0
        scaled = scale * tick_move
        factor = (scaled - 90.0) / scaled
        cursor += tick_move * factor
        lazy_distance += scaled * factor
        lazy_move = 192.8 - cursor
        scaled = scale * lazy_move
        factor = (scaled - 90.0) / scaled
        cursor += lazy_move * factor
        lazy_distance += scaled * factor
        self.assertAlmostEqual(row["ls.lazy_end_position_x_px"], 64.0 + cursor, places=6)
        self.assertAlmostEqual(row["ls.lazy_end_position_y_px"], 64.0, places=6)
        self.assertAlmostEqual(row["ls.lazy_travel_distance_cs_normalised"], lazy_distance, places=6)
        self.assertAlmostEqual(row["ls.travel_time_ms"], 964.0, places=6)
        self.assertAlmostEqual(row["ls.travel_distance_cs_normalised"], lazy_distance, places=6)

    def test_repeat_slider_span_count_and_lazy(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,2,0,L|264:64,2,200,0:0:0:0:\n"
        )
        row = _object(text, 0)
        self.assertEqual(row["ls.slider_span_count"], 2)
        self.assertAlmostEqual(row["ls.slider_duration_ms"], 1000.0, places=6)
        self.assertEqual(row["ls.slider_tick_count"], 2)
        self.assertEqual(row["ls.slider_nested_object_count"], 5)
        radius = circle_size_scale_radius(4.0)[1]
        scale = 50.0 / radius
        cursor = 0.0
        lazy_distance = 0.0
        for target, required in ((100.0, 90.0), (200.0, 50.0), (100.0, 90.0), (14.4, 90.0)):
            move = target - cursor
            m = abs(move)
            scaled = scale * m
            if scaled <= required:
                continue
            factor = (scaled - required) / scaled
            cursor += move * factor
            lazy_distance += scaled * factor
        self.assertAlmostEqual(row["ls.lazy_end_position_x_px"], 64.0 + cursor, places=6)
        self.assertAlmostEqual(row["ls.lazy_travel_distance_cs_normalised"], lazy_distance, places=6)
        self.assertAlmostEqual(
            row["ls.travel_distance_cs_normalised"],
            lazy_distance * max(1.0, 2.0 ** 0.3),
            places=6,
        )

    def test_minimum_jump_time_uses_previous_lazy_travel(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,2,0,L|264:64,1,200,0:0:0:0:\n"
            "300,300,1900,1,0\n"
        )
        row = _object(text, 1)
        self.assertEqual(row["ls.adjusted_delta_time_ms"], 900.0)
        # previous lazy travel = 964 -> max(900-964, 25) = 25
        self.assertEqual(row["ls.minimum_jump_time_ms"], 25.0)

    def test_minimum_jump_distance_tail_and_lazy(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,2,0,L|264:64,1,200,0:0:0:0:\n"
            "300,300,2500,1,0\n"
        )
        row = _object(text, 1)
        lazy = row["ls.lazy_jump_distance_cs_normalised"]
        radius = circle_size_scale_radius(4.0)[1]
        scale = 50.0 / radius
        tail_x = 264.0
        tail_jump = math.hypot(300 - tail_x, 300 - 64) * scale
        expected = max(0.0, min(lazy - (120.0 - 90.0), tail_jump - 120.0))
        self.assertAlmostEqual(row["ls.minimum_jump_distance_cs_normalised"], expected, places=6)


class AngleTests(unittest.TestCase):
    def test_sharp_reversal_angle_is_zero(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "164,64,1500,1,0\n"
            "64,64,2000,1,0\n"
        )
        row = _object(text, 2)
        self.assertEqual(row["ls.slider_aware_angle_rad"], 0.0)
        self.assertEqual(row["ls.normalised_vector_angle_rad"], 0.0)

    def test_continuing_straight_angle_is_pi(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "164,64,1500,1,0\n"
            "264,64,2000,1,0\n"
        )
        row = _object(text, 2)
        self.assertEqual(row["ls.slider_aware_angle_rad"], math.pi)
        self.assertEqual(row["ls.normalised_vector_angle_rad"], 0.0)

    def test_right_angle_is_pi_over_2(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "164,64,1500,1,0\n"
            "164,164,2000,1,0\n"
        )
        row = _object(text, 2)
        self.assertAlmostEqual(row["ls.slider_aware_angle_rad"], math.pi / 2, places=6)
        self.assertAlmostEqual(row["ls.normalised_vector_angle_rad"], math.pi / 2, places=6)

    def test_slider_aware_angle_uses_second_last_nested(self):
        # Previous slider with travel > 0 forces the angle to use the slider
        # head; the result must stay a finite value <= pi.
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "164,64,1500,2,0,L|264:64,1,200,0:0:0:0:\n"
            "164,300,3000,1,0\n"
        )
        row = _object(text, 2)
        angle = row["ls.slider_aware_angle_rad"]
        self.assertIsNotNone(angle)
        self.assertGreaterEqual(angle, 0.0)
        self.assertLessEqual(angle, math.pi)
        self.assertIsNotNone(row["ls.normalised_vector_angle_rad"])


class ReactionTests(unittest.TestCase):
    def test_preempt_formulas(self):
        self.assertEqual(approach_rate_preempt_ms(5.0), 1200)
        self.assertEqual(approach_rate_preempt_ms(0.0), 1800)
        self.assertEqual(approach_rate_preempt_ms(10.0), 450)
        self.assertEqual(approach_rate_preempt_ms(9.0), 600)
        self.assertEqual(approach_rate_preempt_ms(8.5), 675)
        self.assertEqual(approach_rate_preempt_ms(11.0), 300)
        self.assertIsNone(approach_rate_preempt_ms(None))

    def test_hit_window_formulas(self):
        self.assertEqual(overall_difficulty_great_window_ms(0.0), 159.0)
        self.assertEqual(overall_difficulty_great_window_ms(5.0), 99.0)
        self.assertEqual(overall_difficulty_great_window_ms(8.0), 63.0)
        self.assertEqual(overall_difficulty_great_window_ms(10.0), 39.0)
        self.assertIsNone(overall_difficulty_great_window_ms(None))

    def test_missing_ar_preserves_provenance(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
        )
        row = _object(text, 0)
        self.assertIsNone(row["ls.preempt_ms"])
        self.assertIsNone(row["ls.fade_in_ms"])
        self.assertIn("ar_missing", row["ls.provenance"])

    def test_double_tap_feasibility_stacked(self):
        # Stacked circles, 50ms then 150ms deltas, OD8 window 63ms.
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nOverallDifficulty:8\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "64,64,1050,1,0\n"
            "64,64,1200,1,0\n"
        )
        row = _object(text, 1)
        curr, nxt = 50.0, 150.0
        delta_diff = abs(nxt - curr)
        speed_ratio = curr / max(curr, delta_diff)
        window_ratio = min(1.0, curr / 63.0) ** 5
        distance_factor = 1.0  # lazy jump 0 clamps ReverseLerp to 1
        expected = 1.0 - speed_ratio ** (distance_factor * (1.0 - window_ratio))
        self.assertAlmostEqual(row["ls.double_tap_feasibility"], expected, places=9)
        self.assertEqual(_object(text, 2)["ls.double_tap_feasibility"], 0.0)


class SafetyTests(unittest.TestCase):
    def test_no_nan_or_inf_anywhere(self):
        for name in ("minimal.osu", "sliders.osu", "unusual_sv.osu", "timing_changes.osu"):
            out = LocalSignalExtractor().extract(parse_osu_file(FIXTURES / name))
            for row in out["objects"]:
                for key, value in row.items():
                    self.assertTrue(
                        not isinstance(value, float) or math.isfinite(value),
                        f"{name} {key} -> {value!r}",
                    )

    def test_absurd_finite_coordinates_get_provenance_not_nan(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "1.5e308,0,1000,1,0\n"
            "-1.5e308,0,2000,1,0\n"
            "1.5e308,1.5e308,3000,1,0\n"
        )
        out = _extract(text)
        rows = out["objects"]
        self.assertIsNone(rows[1]["ls.jump_distance_raw_px"])
        self.assertIn("jump_distance_nonfinite", rows[1]["ls.provenance"])
        for row in rows:
            for key, value in row.items():
                self.assertTrue(not isinstance(value, float) or math.isfinite(value))

    def test_pathological_high_degree_slider_is_blocked_with_provenance(self):
        # A single Bezier slider with thousands of control points would make
        # adaptive subdivision O(n^2) per level and effectively never finish.
        # The guard must refuse to flatten it: missing geometry + provenance,
        # never a hang and never a fabricated path.
        points = "|".join(f"{80 + (i % 100) * 2}:{64 + (i % 7) * 3}" for i in range(5000))
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            f"[HitObjects]\n64,64,1000,2,0,B|{points},1,200,0:0:0:0:\n"
        )
        rows = _extract(text)["objects"]
        row = rows[0]
        self.assertIsNone(row["ls.slider_duration_ms"])
        self.assertIsNone(row["ls.slider_velocity_px_per_ms"])
        self.assertIsNone(row["ls.lazy_travel_distance_cs_normalised"])
        self.assertIsNone(row["ls.travel_distance_cs_normalised"])
        self.assertIn("path_blocked:control_points_exceeded", row["ls.provenance"])
        for key, value in row.items():
            self.assertTrue(not isinstance(value, float) or math.isfinite(value))

    def test_pathological_tick_rate_is_blocked_with_provenance(self):
        # An absurd SliderTickRate makes tick_distance denormal-small; the
        # tick loop would otherwise run effectively forever.
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1e12\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n64,64,1000,2,0,L|264:64,1,200,0:0:0:0:\n"
        )
        row = _object(text, 0)
        self.assertIn("slider_tick_count_exceeded", row["ls.provenance"])
        self.assertIsNone(row["ls.slider_duration_ms"])
        self.assertIsNone(row["ls.lazy_travel_distance_cs_normalised"])
        for key, value in row.items():
            self.assertTrue(not isinstance(value, float) or math.isfinite(value))

    def test_pathological_slider_spans_are_blocked_with_provenance(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1\nSliderTickRate:1\n"
            "[TimingPoints]\n1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n64,64,1000,2,0,L|264:64,20000,200,0:0:0:0:\n"
        )
        row = _object(text, 0)
        self.assertTrue(any(p.startswith("slider_spans_exceeded:") for p in row["ls.provenance"]))
        self.assertIsNone(row["ls.slider_duration_ms"])
        for key, value in row.items():
            self.assertTrue(not isinstance(value, float) or math.isfinite(value))

    def test_deterministic_repeat(self):
        out1 = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(parse_osu_file(FIXTURES / "sliders.osu"))
        out2 = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(parse_osu_file(FIXTURES / "sliders.osu"))
        self.assertEqual(out1, out2)

    def test_out_of_order_times_preserve_both_indices(self):
        text = (
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
            "192,192,50000,1,0\n"
            "128,128,2000,1,0\n"
        )
        rows = _extract(text)["objects"]
        self.assertEqual([r["ls.time_sorted_index"] for r in rows], [0, 2, 1])
        self.assertEqual([r["ls.original_index"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[2]["ls.last_object_end_delta_time_ms"], 25.0)

    def test_legacy_v3_timing_point(self):
        text = (
            "osu file format v3\n"
            "[Difficulty]\nCircleSize:4\nSliderMultiplier:1.4\nSliderTickRate:1\n"
            "[TimingPoints]\n"
            "1000,500,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,2,0,L|164:64,1,100,0:0:0:0:\n"
            "64,64,3000,1,0\n"
        )
        out = _extract(text)
        self.assertEqual(out["object_count"], 2)
        row = out["objects"][0]
        self.assertIsNotNone(row["ls.slider_duration_ms"])
        # pixel 100 / (1.4*100*1) * 500 beat length
        self.assertAlmostEqual(row["ls.slider_duration_ms"], 100.0 / (1.4 * 100.0) * 500.0, places=6)


class SegmentTests(unittest.TestCase):
    def test_segment_aggregation_covers_all_objects(self):
        out = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(parse_osu_file(FIXTURES / "sliders.osu"))
        segments = out["segments"]
        self.assertEqual(sum(seg["object_count"] for seg in segments), out["object_count"])
        for segment in segments:
            self.assertGreater(segment["end_idx"], segment["start_idx"])
            self.assertIn("ls.jump_distance_cs_normalised", segment["aggregates"])
            agg = segment["aggregates"]["ls.jump_distance_cs_normalised"]
            self.assertGreaterEqual(agg["max"], agg["p90"])
            for value in agg.values():
                self.assertTrue(math.isfinite(value))
            self.assertIn("ls.lazy_travel_time_ms", segment["aggregates"])

    def test_segment_empty_map(self):
        self.assertEqual(segment_local_signals([]), [])


class ContractTests(unittest.TestCase):
    def test_every_emitted_key_is_in_schema(self):
        out = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(parse_osu_file(FIXTURES / "minimal.osu"))
        for row in out["objects"]:
            for key in row:
                self.assertIn(key, SIGNAL_SCHEMA_V02, f"unknown signal {key}")

    def test_v01_duplicate_aliases_hold(self):
        nmap = normalize(parse_osu_file(FIXTURES / "sliders.osu"))
        features = FeatureExtractor().extract(nmap)
        for deprecated, canonical, _reason in DUPLICATE_ALIASES:
            self.assertEqual(features[deprecated], features[canonical])

    def test_migration_table_shape(self):
        table = migration_table()
        self.assertEqual(table["from_feature_version"], "0.1.0")
        self.assertEqual(table["to_feature_version"], "0.2.0")
        self.assertEqual(len(table["duplicate_aliases"]), 3)


class ComplexityTests(unittest.TestCase):
    def test_extraction_scales_linearly_not_quadratically(self):
        def build(n: int) -> str:
            lines = [
                "osu file format v14",
                "[Difficulty]\nCircleSize:4\nSliderMultiplier:1.4\nSliderTickRate:2",
                "[TimingPoints]\n1000,500,4,2,1,60,1,0",
                "[HitObjects]",
            ]
            for i in range(n):
                lines.append(f"{64 + (i % 8) * 40},{64 + ((i // 8) % 8) * 40},{1000 + i * 50},1,0")
            return "\n".join(lines)

        timings = []
        for n in (1000, 2000, 4000, 8000):
            text = build(n)
            start = time.perf_counter()
            LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(parse_osu(text))
            timings.append(time.perf_counter() - start)
        # 8k must not be anywhere near 64x slower than 1k; generous bound of 32x.
        self.assertLess(timings[3], max(32.0 * timings[0], 8.0))


if __name__ == "__main__":
    unittest.main()

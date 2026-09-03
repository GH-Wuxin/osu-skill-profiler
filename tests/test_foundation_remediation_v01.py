"""Independent regressions for Pre-ML Foundation Remediation v0.1.

Expected values here are hand-derived from the .osu span-count field and the
pinned slider equations.  The expected side deliberately does not import the
production slider-semantics helper.
"""

from __future__ import annotations

import math
import unittest

from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.features.schema import LEGACY_FEATURE_VERSION
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu
from osu_skill_profiler.reference.ppy import evaluators as reference_evaluators
from osu_skill_profiler.reference.ppy.contract import (
    LEGACY_REFERENCE_VERSION,
    REFERENCE_VERSION,
)
from osu_skill_profiler.reference.ppy.preprocess import RefObject, build_ref_objects
from osu_skill_profiler.reference.ppy.extractor import ReferenceSignalExtractor
from osu_skill_profiler.signals.contract import (
    LEGACY_SIGNAL_VERSION,
    PREVIOUS_SIGNAL_VERSION,
    SIGNAL_VERSION,
)
from osu_skill_profiler.signals.extractor import LocalSignalExtractor
from osu_skill_profiler.signals.path import build_slider_path


def _map(
    objects: list[str],
    *,
    timing: list[str] | None = None,
    file_version: int = 14,
    tick_rate: float = 1.0,
) -> str:
    timing = timing or ["0,500,4,2,1,60,1,0"]
    return "\n".join(
        [
            f"osu file format v{file_version}",
            "[General]",
            "Mode:0",
            "[Difficulty]",
            "CircleSize:4",
            "OverallDifficulty:8",
            "ApproachRate:9",
            "SliderMultiplier:1",
            f"SliderTickRate:{tick_rate}",
            "[TimingPoints]",
            *timing,
            "[HitObjects]",
            *objects,
        ]
    ) + "\n"


def _slider(time_ms: float, spans: int, length: float = 200.0) -> str:
    return f"64,64,{time_ms},2,0,L|264:64,{spans},{length},0:0:0:0:"


def _ref_circle(index: int, start_time_ms: float) -> RefObject:
    return RefObject(
        original_index=index,
        time_sorted_index=index,
        start_time_ms=start_time_ms,
        end_time_ms=start_time_ms,
        object_type="circle",
        delta_time_ms=None if index == 0 else 100.0,
        adjusted_delta_time_ms=None if index == 0 else 100.0,
        last_object_end_delta_time_ms=None if index == 0 else 100.0,
        minimum_jump_time_ms=None if index == 0 else 100.0,
        preempt_ms=600.0,
        fade_in_ms=400.0,
        hit_window_great_ms=63.0,
        radius_px=36.5,
        cs_scale=50.0 / 36.5,
        small_circle_bonus=1.0,
        position=(float(index % 2) * 200.0, 0.0),
        lazy_end_position=None,
        tail_position=None,
        jump_distance_cs=None if index == 0 else 200.0,
        lazy_jump_distance_cs=None if index == 0 else 200.0,
        minimum_jump_distance_cs=None if index == 0 else 200.0,
        lazy_travel_distance_cs=0.0,
        lazy_travel_time_ms=0.0,
        travel_distance_cs=0.0,
        travel_time_ms=0.0,
        angle_rad=None,
        normalised_vector_angle_rad=None,
        double_tap_feasibility=None if index == 0 else 0.0,
        spinner_context=False,
        geometry_blocked=False,
        provenance=(),
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _smootherstep(value: float, start: float, end: float) -> float:
    x = _clamp((value - start) / (end - start), 0.0, 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


class CanonicalSliderSemanticsTests(unittest.TestCase):
    def test_count_relationship_for_malformed_zero_and_multiple_spans(self):
        beatmap = parse_osu(_map([_slider(0, 0), _slider(1000, 1), _slider(2000, 2), _slider(3000, 4)]))
        objects = normalize(beatmap).objects
        self.assertEqual([obj.slider_span_count for obj in objects], [1, 1, 2, 4])
        self.assertEqual([obj.slider_repeat_count for obj in objects], [0, 0, 1, 3])

    def test_total_duration_and_end_time_across_span_counts(self):
        # 200px / (100px per beat / 500ms) = 1000ms per span.
        beatmap = parse_osu(_map([_slider(0, 1), _slider(4000, 2), _slider(8000, 3)]))
        nmap = normalize(beatmap)
        expected_totals = [1000.0, 2000.0, 3000.0]
        self.assertEqual([obj.slider_single_span_duration_ms for obj in nmap.objects], [1000.0] * 3)
        self.assertEqual([obj.slider_total_duration_ms for obj in nmap.objects], expected_totals)
        self.assertEqual([obj.canonical_end_time_ms() for obj in nmap.objects], [1000.0, 6000.0, 11000.0])

        feature = FeatureExtractor().extract(nmap)
        self.assertEqual(feature["slider.duration_ms_mean"], 2000.0)
        self.assertEqual(feature["slider.repeat_count_total"], 3.0)
        self.assertEqual(feature["slider.repeat_count_max"], 2.0)
        self.assertEqual(feature["slider.span_count_total"], 6.0)
        self.assertEqual(feature["slider.span_count_max"], 3.0)

        rows = LocalSignalExtractor().extract(beatmap)["objects"]
        self.assertEqual([row["ls.slider_total_duration_ms"] for row in rows], expected_totals)
        self.assertEqual([row["ls.slider_duration_ms"] for row in rows], expected_totals)
        self.assertEqual([row["ls.end_time_ms"] for row in rows], [1000.0, 6000.0, 11000.0])

    def test_odd_even_span_tail_parity_and_repeat_nested_count(self):
        beatmap = parse_osu(_map([_slider(0, 2), _slider(4000, 3)]))
        geometries = []
        LocalSignalExtractor()._extract_rows(beatmap, _geometries_out=geometries)  # noqa: SLF001
        two, three = geometries
        self.assertEqual(two.repeat_count, 1)
        self.assertEqual(three.repeat_count, 2)
        self.assertEqual(sum(event.kind == "repeat" for event in two.nested), 1)
        self.assertEqual(sum(event.kind == "repeat" for event in three.nested), 2)
        self.assertAlmostEqual(two.tail_position[0], 64.0)
        self.assertAlmostEqual(three.tail_position[0], 264.0)

    def test_slider_to_circle_and_slider_to_slider_use_total_end(self):
        beatmap = parse_osu(
            _map(
                [
                    "64,64,0,1,0",
                    _slider(1000, 2),       # ends 3000
                    "300,200,3500,1,0",    # 500ms after end
                    _slider(4000, 3),       # ends 7000
                    _slider(7100, 1),       # 100ms after end
                ]
            )
        )
        rows = LocalSignalExtractor().extract(beatmap)["objects"]
        self.assertEqual(rows[2]["ls.last_object_end_delta_time_ms"], 500.0)
        self.assertEqual(rows[4]["ls.last_object_end_delta_time_ms"], 100.0)

    def test_inherited_timing_and_sv(self):
        # Green -50 timing point means 2x SV; one span becomes 500ms.
        beatmap = parse_osu(
            _map(
                [_slider(1000, 2)],
                timing=["0,500,4,2,1,60,1,0", "500,-50,4,2,1,60,0,0"],
            )
        )
        row = LocalSignalExtractor().extract(beatmap)["objects"][0]
        self.assertAlmostEqual(row["ls.slider_velocity_px_per_ms"], 0.4)
        self.assertAlmostEqual(row["ls.slider_single_span_duration_ms"], 500.0)
        self.assertAlmostEqual(row["ls.slider_total_duration_ms"], 1000.0)

    def test_old_format_and_short_long_finite_sliders(self):
        old = parse_osu(_map([_slider(1000, 2, 100.0)], file_version=3))
        old_row = LocalSignalExtractor().extract(old)["objects"][0]
        self.assertEqual(old_row["ls.slider_total_duration_ms"], 1000.0)

        finite = parse_osu(_map([_slider(0, 1, 1.0), _slider(10000, 4, 100000.0)]))
        rows = LocalSignalExtractor().extract(finite)["objects"]
        self.assertEqual(rows[0]["ls.slider_total_duration_ms"], 5.0)
        self.assertEqual(rows[1]["ls.slider_total_duration_ms"], 2_000_000.0)
        for row in rows:
            for value in row.values():
                self.assertFalse(isinstance(value, float) and not math.isfinite(value))


class VersionBoundaryAndMutationTests(unittest.TestCase):
    def test_feature_v01_is_historical_and_v02_is_unambiguous(self):
        beatmap = parse_osu(_map([_slider(0, 1), _slider(4000, 3)]))
        nmap = normalize(beatmap)
        legacy = FeatureExtractor(LEGACY_FEATURE_VERSION).extract(nmap)
        current = FeatureExtractor().extract(nmap)
        self.assertEqual(legacy["slider.repeats_total"], 4.0)
        self.assertEqual(legacy["slider.repeats_max"], 3.0)
        self.assertEqual(current["slider.repeat_count_total"], 2.0)
        self.assertEqual(current["slider.repeat_count_max"], 2.0)
        self.assertEqual(current["slider.span_count_total"], 4.0)
        self.assertNotIn("slider.repeats_total", current)

    def test_local_v02_v03_replay_and_v04_corrected_geometry(self):
        beatmap = parse_osu(_map([_slider(1000, 2)]))
        legacy = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(beatmap)
        previous = LocalSignalExtractor(PREVIOUS_SIGNAL_VERSION).extract(beatmap)
        current = LocalSignalExtractor(SIGNAL_VERSION).extract(beatmap)
        self.assertEqual(legacy["signal_version"], "0.2.0")
        self.assertEqual(previous["signal_version"], "0.3.0")
        self.assertEqual(current["signal_version"], "0.4.0")
        self.assertEqual(legacy["objects"][0]["ls.slider_duration_ms"], 1000.0)
        self.assertNotIn("ls.slider_repeat_count", legacy["objects"][0])
        self.assertEqual(previous["objects"][0]["ls.slider_duration_ms"], 2000.0)
        self.assertEqual(current["objects"][0]["ls.slider_duration_ms"], 2000.0)
        self.assertEqual(current["objects"][0]["ls.slider_repeat_count"], 1)

    def test_local_v04_splits_compound_bezier_at_duplicate_anchor(self):
        points = ((0.0, 0.0), (31.0, 24.0), (31.0, 24.0), (-188.0, -16.0))
        previous = build_slider_path(
            "B",
            points,
            240.0,
            split_bezier_segments=False,
        )
        current = build_slider_path(
            "B",
            points,
            240.0,
            split_bezier_segments=True,
        )

        first_length = math.hypot(31.0, 24.0)
        second_dx, second_dy = -219.0, -40.0
        second_length = math.hypot(second_dx, second_dy)
        progress = (240.0 - first_length) / second_length
        expected_tail = (
            31.0 + second_dx * progress,
            24.0 + second_dy * progress,
        )

        self.assertAlmostEqual(current.position_at(1.0)[0], expected_tail[0], places=6)
        self.assertAlmostEqual(current.position_at(1.0)[1], expected_tail[1], places=6)
        self.assertGreater(
            math.dist(previous.position_at(1.0), current.position_at(1.0)),
            30.0,
        )

    def test_local_v04_does_not_split_terminal_bezier_duplicate(self):
        points = ((0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 100.0))
        current = build_slider_path("B", points, None)
        historical_single_segment = build_slider_path(
            "B",
            points,
            None,
            split_bezier_segments=False,
        )
        self.assertEqual(
            current.calculated_path,
            historical_single_segment.calculated_path,
        )

    def test_local_version_selects_compound_bezier_semantics(self):
        beatmap = parse_osu(
            _map(
                [
                    "64,64,1000,2,0,"
                    "B|164:64|164:64|164:164,1,200,0:0:0:0:"
                ]
            )
        )
        previous_geometries = []
        current_geometries = []
        LocalSignalExtractor(PREVIOUS_SIGNAL_VERSION)._extract_rows(
            beatmap,
            _geometries_out=previous_geometries,
        )
        LocalSignalExtractor(SIGNAL_VERSION)._extract_rows(
            beatmap,
            _geometries_out=current_geometries,
        )
        previous_tail = previous_geometries[0].tail_position
        current_tail = current_geometries[0].tail_position
        self.assertAlmostEqual(current_tail[0], 164.0, places=6)
        self.assertAlmostEqual(current_tail[1], 164.0, places=6)
        self.assertGreater(math.dist(previous_tail, current_tail), 10.0)

    def test_local_v04_duplicate_free_bezier_is_unchanged(self):
        points = ((0.0, 0.0), (0.0, 100.0), (100.0, 100.0))
        current = build_slider_path("B", points, None)
        previous = build_slider_path(
            "B",
            points,
            None,
            split_bezier_segments=False,
        )
        self.assertEqual(current.calculated_path, previous.calculated_path)

    def test_local_v04_flattens_each_compound_bezier_segment_independently(self):
        points = (
            (0.0, 0.0),
            (0.0, 100.0),
            (100.0, 100.0),
            (100.0, 100.0),
            (200.0, 100.0),
            (200.0, 0.0),
        )
        current = build_slider_path("B", points, None)
        historical_single_segment = build_slider_path(
            "B",
            points,
            None,
            split_bezier_segments=False,
        )
        self.assertAlmostEqual(current.calculated_distance, 324.6369098333715, places=6)
        self.assertAlmostEqual(current.position_at(0.5)[0], 100.0, places=6)
        self.assertAlmostEqual(current.position_at(0.5)[1], 100.0, places=6)
        self.assertGreater(
            abs(current.calculated_distance - historical_single_segment.calculated_distance),
            10.0,
        )

    def test_historical_duration_and_span_bonus_mutations_are_detected(self):
        beatmap = parse_osu(_map([_slider(1000, 2)]))
        row = LocalSignalExtractor().extract(beatmap)["objects"][0]
        # Historical RT-01 mutation: total duration incorrectly equals one span.
        old_compressed_duration = 200.0 / 0.2
        self.assertNotEqual(row["ls.slider_total_duration_ms"], old_compressed_duration)
        # Historical RT-02 mutation: span_count (2) replaces repeat_count (1).
        lazy = row["ls.lazy_travel_distance_cs_normalised"]
        old_span_bonus_value = lazy * max(1.0, 2.0**0.3)
        expected_repeat_bonus_value = lazy * max(1.0, 1.0**0.3)
        self.assertAlmostEqual(row["ls.travel_distance_cs_normalised"], expected_repeat_bonus_value)
        self.assertNotAlmostEqual(row["ls.travel_distance_cs_normalised"], old_span_bonus_value)

    def test_unsupported_versions_fail_before_extraction(self):
        with self.assertRaises(ValueError):
            FeatureExtractor("9.9.9")
        with self.assertRaises(ValueError):
            LocalSignalExtractor("9.9.9")
        with self.assertRaises(ValueError):
            ReferenceSignalExtractor("9.9.9")

    def test_reference_v01_and_v02_report_honest_versions(self):
        beatmap = parse_osu(_map(["64,64,0,1,0", _slider(1000, 2), "300,200,3500,1,0"]))
        legacy = ReferenceSignalExtractor(LEGACY_REFERENCE_VERSION).extract(beatmap)
        current = ReferenceSignalExtractor(REFERENCE_VERSION).extract(beatmap)
        self.assertEqual(legacy["reference_version"], "0.1.0")
        self.assertEqual(current["reference_version"], "0.2.0")
        self.assertEqual(legacy["object_count"], current["object_count"])
        # This particular evaluator pattern can legitimately gate both
        # versions to the same public values. Verify the semantic dependency
        # at the Reference preprocessing boundary instead: v0.1 consumes the
        # historical one-span Local duration while v0.2 consumes total
        # duration for both spans.
        legacy_objects = build_ref_objects(beatmap, LEGACY_REFERENCE_VERSION)
        current_objects = build_ref_objects(beatmap, REFERENCE_VERSION)
        self.assertEqual(legacy_objects[1].end_time_ms, 2000.0)
        self.assertEqual(current_objects[1].end_time_ms, 3000.0)


class ReferenceReadingIdentityTests(unittest.TestCase):
    def test_current_object_opacity_at_past_object_time(self):
        objects = [_ref_circle(index, 1400.0 + index * 100.0) for index in range(8)]
        current_index = 6
        current = objects[current_index]

        expected_terms = []
        for loop_index in range(5, 0, -1):
            loop = objects[loop_index]
            fade_in_start = current.start_time_ms - 600.0
            opacity = _clamp(
                (loop.start_time_ms - fade_in_start) / 400.0,
                0.0,
                1.0,
            )
            distance = _smootherstep(200.0, 15.0, 150.0)
            time_nerf = _clamp(
                2.0 - (current.start_time_ms - loop.start_time_ms) / 1500.0,
                0.0,
                1.0,
            )
            expected_terms.append(opacity * distance * time_nerf)
        expected_past = sum(expected_terms)

        corrected_past = reference_evaluators._past_object_difficulty_influence(  # noqa: SLF001
            objects,
            current_index,
            current,
            reference_version=REFERENCE_VERSION,
        )
        legacy_past = reference_evaluators._past_object_difficulty_influence(  # noqa: SLF001
            objects,
            current_index,
            current,
            reference_version=LEGACY_REFERENCE_VERSION,
        )
        self.assertAlmostEqual(corrected_past, expected_past, places=12)
        self.assertNotAlmostEqual(legacy_past, expected_past, places=12)

        future_influence = math.sqrt(1.0) * _smootherstep(200.0, 15.0, 150.0)
        note_density = (expected_past + future_influence) ** 1.7 * 0.4 * 2.0
        note_density = max(0.0, note_density - 2.5) ** 0.45 * 2.4
        high_bpm = 1.0 / (1.0 - 0.8**0.1)
        expected_reading = note_density * high_bpm
        corrected_reading = reference_evaluators.reading(
            objects,
            current_index,
            reference_version=REFERENCE_VERSION,
        )
        legacy_reading = reference_evaluators.reading(
            objects,
            current_index,
            reference_version=LEGACY_REFERENCE_VERSION,
        )
        self.assertAlmostEqual(corrected_reading, expected_reading, places=9)
        self.assertNotAlmostEqual(legacy_reading, expected_reading, places=9)


if __name__ == "__main__":
    unittest.main()

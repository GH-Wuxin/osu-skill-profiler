"""Behavioral checks for the opt-in Flow execution model, not rating targets.

Fixtures use actual Local Signal extraction over in-memory circle maps.  Their
coordinates, distances, and angles agree; no legacy synthetic angle overrides
are used to manufacture an expected winner.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "tools", ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01 import flow_execution_v02 as flow  # noqa: E402
from osu_skill_profiler.parser.osu_parser import parse_osu  # noqa: E402
from osu_skill_profiler.signals.extractor import LocalSignalExtractor  # noqa: E402


def orbit(
    transitions: int = 32,
    *,
    distance: float = 70.0,
    turn: float = math.pi / 8.0,
) -> list[tuple[float, float]]:
    """A bounded, constant-chord circle sequence with no turnaround seam."""
    radius = distance / (2.0 * math.sin(turn / 2.0))
    return [
        (256.0 + radius * math.cos(i * turn), 192.0 + radius * math.sin(i * turn))
        for i in range(transitions + 1)
    ]


def extract_rows(
    points: list[tuple[float, float]],
    *,
    interval: float = 100.0,
    intervals: list[float] | None = None,
    circle_size: float = 4.0,
    spinner_at: int | None = None,
    slider_at: int | None = None,
) -> list[dict]:
    if intervals is not None and len(intervals) != len(points) - 1:
        raise ValueError("one interval is required for each transition")
    time = 1000.0
    objects = []
    for i, (x, y) in enumerate(points):
        if i:
            time += interval if intervals is None else intervals[i - 1]
        if i == spinner_at:
            objects.append(f"{x:.15g},{y:.15g},{time:.15g},8,0,{time + 50:.15g}")
        elif i == slider_at:
            end_x, end_y = points[i + 1]
            length = math.hypot(end_x - x, end_y - y)
            objects.append(f"{x:.15g},{y:.15g},{time:.15g},2,0,L|{end_x:.15g}:{end_y:.15g},1,{length:.15g}")
        else:
            objects.append(f"{x:.15g},{y:.15g},{time:.15g},1,0")
    text = (
        "osu file format v14\n[General]\nMode:0\n"
        "[Metadata]\nTitle:Flow behavior fixture\nArtist:Test\nCreator:Test\nVersion:Test\n"
        f"[Difficulty]\nCircleSize:{circle_size}\nApproachRate:9\nOverallDifficulty:8\n"
        "HPDrainRate:5\nSliderMultiplier:1.4\nSliderTickRate:1\n"
        "[TimingPoints]\n0,400,4,2,1,100,1,0\n[HitObjects]\n"
        + "\n".join(objects)
        + "\n"
    )
    beatmap = parse_osu(text)
    rows = LocalSignalExtractor().extract(beatmap)["objects"]
    return [
        {**row, "v091.start_x_px": obj.x, "v091.start_y_px": obj.y}
        for row, obj in zip(rows, beatmap.hit_objects)
    ]


def measure(rows, *, circle_size=4.0, mods=()):
    return flow.extract_flow_measure(
        rows, effective_mods=mods, circle_size=circle_size
    )


class FlowExecutionMechanismTests(unittest.TestCase):
    def test_supported_turn_adjustment_adds_control_without_changing_motion(self):
        def points(turns):
            x = y = heading = 0.0
            result = [(x, y)]
            for i in range(32):
                x += 70.0 * math.cos(heading)
                y += 70.0 * math.sin(heading)
                result.append((x, y))
                heading += math.radians(turns[i % len(turns)])
            cx = (min(x for x, y in result) + max(x for x, y in result)) / 2
            cy = (min(y for x, y in result) + max(y for x, y in result)) / 2
            centered = [(x - cx + 256, y - cy + 192) for x, y in result]
            self.assertTrue(all(0 <= x <= 512 and 0 <= y <= 384 for x, y in centered))
            return centered

        # Both closed paths use 70px / 100ms at CS4. Alternating established
        # bends add a local adjustment; neither spacing nor rate changes.
        regular = measure(extract_rows(points([45.0])))
        adjusted = measure(extract_rows(points([30.0, 60.0])))
        # This assertion concerns local turn adjustment, independently of
        # whether a sustained candidate now wins the public Flow value.
        a, b = regular["signals"]["local_peak"], adjusted["signals"]["local_peak"]
        self.assertAlmostEqual(a["movement_execution_intensity"], b["movement_execution_intensity"], places=10)
        self.assertAlmostEqual(a["local_control_increment"], 0.0, places=10)
        self.assertGreater(b["local_control_increment"], 0.0)
        self.assertGreater(adjusted["value"], regular["value"])
        self.assertTrue(b["control_source_within_candidate"])
        self.assertFalse(b["spatial_reentry_classified"])

    def test_real_smooth_curve_has_observed_positive_demand(self):
        result = measure(extract_rows(orbit()))
        self.assertEqual(result["status"], "FULL")
        self.assertEqual(result["coverage"], 1.0)
        self.assertGreater(result["value"], 0.0)
        winner = result["winning_section"]
        self.assertGreater(winner["execution_intensity"], 0.0)
        self.assertGreater(winner["duration_ms"], 0.0)
        self.assertGreater(winner["chain_support"], 0.0)
        self.assertLessEqual(winner["chain_support"], 1.0)

    def test_equal_distance_time_reversals_do_not_outrank_smooth_flow(self):
        smooth = measure(extract_rows(orbit(distance=70.0)))
        # Every reversal has exactly the same 70px/100ms as the smooth chord.
        reversals = [(221.0 if i % 2 else 291.0, 192.0) for i in range(33)]
        abrupt = measure(extract_rows(reversals))
        self.assertEqual(abrupt["status"], "FULL")
        self.assertLess(abrupt["value"], smooth["value"])

    def test_extending_regular_flow_does_not_create_execution_intensity(self):
        shorter = measure(extract_rows(orbit(32)))
        longer = measure(extract_rows(orbit(128)))
        short = shorter["winning_section"]
        long = longer["winning_section"]
        self.assertAlmostEqual(
            short["execution_intensity"], long["execution_intensity"], places=9
        )
        self.assertAlmostEqual(
            short["raw_peak_intensity"], long["raw_peak_intensity"], places=9
        )
        for section in (short, long):
            self.assertGreaterEqual(section["chain_support"], 0.0)
            self.assertLessEqual(section["chain_support"], 1.0)

    def test_supported_short_hard_curve_can_exceed_long_easy_curve(self):
        hard = measure(extract_rows(orbit(16, distance=100.0, turn=math.pi / 3)))
        easy = measure(
            extract_rows(orbit(128, distance=35.0, turn=math.pi / 3), interval=150.0)
        )
        self.assertGreater(hard["value"], easy["value"])

    def test_single_large_jump_cannot_establish_positive_flow(self):
        result = measure(extract_rows([(64.0, 192.0), (448.0, 192.0)], interval=80.0))
        self.assertIn(result["value"], (None, 0.0))

    def test_fixed_distance_relaxed_deadlines_reduce_demand(self):
        values = [
            measure(extract_rows(orbit(), interval=interval))["value"]
            for interval in (90.0, 180.0, 360.0)
        ]
        self.assertTrue(all(a > b for a, b in zip(values, values[1:])), values)

    def test_expanding_square_jump_excerpt_does_not_borrow_flow_history(self):
        # Human-labelled Altar circle excerpt, also used in reentry tests.
        # Removing history decay globally lets its wide jumps beat the
        # positive, smooth Flow comparator. Spacing/time relief must not.
        points = [(167,156),(295,104),(347,232),(219,284),(201,58),(392,137),
                  (311,330),(120,249),(326,24),(425,265),(182,364),(84,122),
                  (443,116),(331,383),(62,269),(175,2)]
        intervals = [114,114,113,114,114,114,113,113,114,114,113,114,114,114,113]
        jumps = measure(extract_rows(points, intervals=intervals))
        smooth = measure(extract_rows(orbit(16, distance=70), interval=114))
        self.assertLess(jumps["value"], smooth["value"])

    def test_corner_history_depends_on_spacing_and_absolute_time(self):
        def section(distance, interval):
            return measure(extract_rows(
                orbit(32, distance=distance, turn=math.pi / 2), interval=interval
            ))["winning_section"]
        compact = section(24, 100)
        wide = section(100, 100)
        relaxed = section(100, 180)
        # Same 90-degree arrangement; direction alone does not determine
        # whether previous movements retain substantial local support.
        self.assertGreater(compact["support"], wide["support"])
        self.assertGreater(wide["support"], relaxed["support"])
        self.assertGreater(wide["value"], relaxed["value"])

    def test_history_relief_handles_extreme_finite_physical_inputs(self):
        enormous = {"distance": 1e300, "time_ms": 1e300}
        tiny = {"distance": 1e-300, "time_ms": 1e-300}
        self.assertEqual(flow._history_relief(enormous, tiny), 0.0)
        self.assertEqual(flow._history_relief(tiny, enormous), 0.0)
        self.assertEqual(flow._history_relief(tiny, tiny), 1.0)

    def test_nonflow_jumps_cannot_borrow_easy_chain_support(self):
        # Both 400px jumps reverse the current direction completely. Their
        # local Flow membership is zero; eight cheap, straight 4px motions
        # between them must not establish either jump's execution intensity.
        # All points remain inside the normal playfield.
        x = 100.0
        points = [(x, 192.0)]
        intervals = []
        for step, interval, count in (
            (-4.0, 100.0, 8),
            (400.0, 25.0, 1),
            (4.0, 100.0, 8),
            (-400.0, 25.0, 1),
            (-4.0, 100.0, 8),
        ):
            for _ in range(count):
                x += step
                points.append((x, 192.0))
                intervals.append(interval)
        mixed = measure(extract_rows(points, intervals=intervals))
        cheap_only = measure(
            extract_rows([(256.0 - i * 4.0, 192.0) for i in range(27)])
        )
        self.assertLessEqual(mixed["value"], cheap_only["value"] + 1e-9)

    def test_supported_variable_spacing_retains_harder_transitions(self):
        def points(variable):
            angle = 0.0
            result = []
            for i in range(33):
                if i:
                    angle += math.pi / 4 if variable and i % 2 == 0 else math.pi / 8
                result.append(
                    (256.0 + 120.0 * math.cos(angle), 192.0 + 120.0 * math.sin(angle))
                )
            return result

        # Both patterns remain within the field with gentle, well-supported
        # directions and identical 100ms deadlines. The second expands every
        # other chord from about 46.8px to 91.8px; a smaller neighboring step
        # must not completely erase these recurring harder movements.
        constant = measure(extract_rows(points(False)))
        variable = measure(extract_rows(points(True)))
        # This tolerance excludes floating-point noise, not a rating target.
        self.assertGreater(variable["value"] - constant["value"], 1e-8)

    def test_nearly_reversing_owned_movements_tend_to_zero(self):
        def value(delta_y):
            return measure(
                extract_rows(
                    [
                        (104.0, 192.0),
                        (100.0, 192.0),
                        (500.0, 192.0 + delta_y),
                        (100.0, 192.0 + 2.0 * delta_y),
                        (96.0, 192.0 + 2.0 * delta_y),
                    ],
                    intervals=[100.0, 25.0, 25.0, 100.0],
                )
            )["value"]

        # The two high intensities have almost no directional ownership.
        # Normalizing their estimate must not cancel that absolute lack of
        # evidence and create a finite plateau immediately beside reversal.
        values = [value(delta) for delta in (1.0, 0.01, 0.0001, 0.000001, 0.0)]
        self.assertEqual(values[-1], 0.0)
        self.assertTrue(all(a >= b for a, b in zip(values, values[1:])), values)
        self.assertAlmostEqual(values[-2], values[-1], delta=1e-10)


class SustainedFlowTests(unittest.TestCase):
    def test_gain_calibration_preserves_load_and_applies_to_reentry_too(self):
        from tests.test_flow_reentry_execution_v01 import two_phrases
        for points in (orbit(64), two_phrases()):
            rows = extract_rows(points)
            with mock.patch.object(flow, "FLOW_LOG_GAIN", 1.55):
                before = measure(rows)
            after = measure(rows)
            self.assertGreater(after["value"], before["value"])
            for key in ("supported_execution_load", "start_ms", "end_ms", "kind"):
                self.assertEqual(after["winning_section"][key], before["winning_section"][key])
            reentry = after["signals"]["spatial_reentry"]["best_candidate"]
            if reentry:
                self.assertAlmostEqual(reentry["value"], flow._load_value(reentry["supported_execution_load"]))
        self.assertEqual(flow._load_value(0), 0)

    def test_easy_movements_cannot_dilute_or_establish_a_harder_intensity_level(self):
        hard = flow._supported_intensity([2.0] * 6, [1.0] * 6)[0]
        mixed = flow._supported_intensity([2.0] * 6 + [0.2] * 20, [1.0] * 26)[0]
        self.assertGreaterEqual(mixed, hard)
        self.assertLessEqual(mixed - hard, 0.2)
        # An isolated extreme must not borrow those twenty cheap links.
        isolated = flow._supported_intensity([200.0] + [0.2] * 20, [1.0] * 21)[0]
        self.assertLessEqual(isolated, 0.2)

    def test_tight_continuous_bends_do_not_need_long_local_history_for_sustained_load(self):
        # All movements have the same physical intensity and continuous
        # 75ms tapping. Shortening the local estimator must not erase the
        # burden already established by the full 128-movement sequence.
        rows = extract_rows(orbit(128, distance=40, turn=math.pi / 2), interval=75)
        ordinary = measure(rows)["signals"]["sustained_flow"]
        with mock.patch.object(flow, "MAX_WINDOW_EVENTS", 8):
            shorter = measure(rows)["signals"]["sustained_flow"]
        self.assertGreater(ordinary["remaining_load"], 0)
        self.assertAlmostEqual(ordinary["remaining_load"], shorter["remaining_load"], places=9)
        self.assertEqual(ordinary["charged_movements"], shorter["charged_movements"])

    def test_length_growth_continues_for_both_fast_and_slow_established_flow(self):
        for interval in (100.0, 200.0):
            for distance in (24.0, 100.0):
                with self.subTest(interval=interval, distance=distance):
                    values = [measure(extract_rows(
                        orbit(count, distance=distance, turn=math.pi / 4), interval=interval
                    ))["value"] for count in (16, 32, 64, 128)]
                    self.assertTrue(all(b > a + 1e-8 for a, b in zip(values, values[1:])), values)

    def test_wide_long_flow_exceeds_either_short_wide_or_long_compact_flow(self):
        def value(distance, count):
            return measure(extract_rows(orbit(count, distance=distance, turn=math.pi / 4)))["value"]
        wide_short, wide_long = value(100, 16), value(100, 128)
        compact_short, compact_long = value(24, 16), value(24, 128)
        self.assertGreater(wide_long, max(wide_short, compact_long))
        self.assertGreater(wide_long - wide_short, compact_long - compact_short)

    def test_overlapping_local_windows_do_not_multiply_sustained_credit(self):
        rows = extract_rows(orbit(128, distance=70))
        ordinary = measure(rows)
        with mock.patch.object(flow, "MAX_WINDOW_EVENTS", 64), mock.patch.object(flow, "MAX_WINDOW_SPAN_MS", 8000.0):
            wider = measure(rows)
        self.assertAlmostEqual(ordinary["value"], wider["value"], places=9)
        self.assertEqual(ordinary["signals"]["sustained_flow"]["charged_movements"],
                         wider["signals"]["sustained_flow"]["charged_movements"])
        self.assertLessEqual(ordinary["signals"]["sustained_flow"]["charged_movements"], len(rows) - 1)

    def test_short_slider_relaxes_but_does_not_erase_previous_flow(self):
        points = orbit(128, distance=70)
        continuous = measure(extract_rows(points))["value"]
        intervals = [100.0] * 128
        intervals[63] = 220.0  # 70px slider duration is 200ms in this fixture.
        brief = measure(extract_rows(points, intervals=intervals, slider_at=63))["value"]
        intervals[63] = 5000.0
        rested = measure(extract_rows(points, intervals=intervals, slider_at=63))["value"]
        self.assertGreater(continuous, brief)
        self.assertGreater(brief, rested)

    def test_known_slider_without_exit_direction_carries_but_missing_geometry_does_not(self):
        from tests.test_flow_geometry_v02 import rows_for
        points = orbit(128, distance=70)
        # Low-level geometry fixture: positive, timed slider travel and a
        # known zero exit vector. This is different from missing its endpoint.
        rows = rows_for(points, sliders={63: (points[64], 50, 70)})
        known = measure(rows)
        broken = copy.deepcopy(rows)
        broken[63]["ls.lazy_end_position_x_px"] = None
        missing = measure(broken)
        self.assertGreater(known["signals"]["sustained_flow"]["remaining_load"],
                           missing["signals"]["sustained_flow"]["remaining_load"])


class FlowExecutionIsolationTests(unittest.TestCase):
    def test_long_gap_does_not_join_two_short_support_chains(self):
        points = orbit(8)
        alone = measure(extract_rows(points))
        together = measure(
            extract_rows(
                points + points,
                intervals=[100.0] * 8 + [5000.0] + [100.0] * 8,
            )
        )
        self.assertLessEqual(together["value"], alone["value"] + 1e-9)
        self.assertLessEqual(
            together["winning_section"]["duration_ms"],
            alone["winning_section"]["duration_ms"] + 1e-9,
        )

    def test_spinner_does_not_join_two_short_support_chains(self):
        points = orbit(8)
        alone = measure(extract_rows(points))
        together = measure(
            extract_rows(points + [(256.0, 192.0)] + points, spinner_at=len(points))
        )
        self.assertLessEqual(together["value"], alone["value"] + 1e-9)

    def test_repeated_distant_section_does_not_sum_local_scores(self):
        points = orbit(32)
        once = measure(extract_rows(points))
        twice = measure(
            extract_rows(
                points + points,
                intervals=[100.0] * 32 + [5000.0] + [100.0] * 32,
            )
        )
        self.assertAlmostEqual(once["value"], twice["value"], places=9)


class FlowExecutionInputContractTests(unittest.TestCase):
    def test_radius_tightening_changes_execution_demand_once(self):
        values = [
            measure(extract_rows(orbit(), circle_size=cs), circle_size=cs)["value"]
            for cs in (4.0, 5.2, 6.0)
        ]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])), values)

    def test_effective_mod_labels_do_not_retransform_existing_geometry(self):
        rows = extract_rows(orbit(), circle_size=5.2)
        baseline = measure(rows, circle_size=5.2)
        for mods in (("HD",), ("HR",), ("HD", "HR"), ("HD", "DT")):
            with self.subTest(mods=mods):
                result = measure(rows, circle_size=5.2, mods=mods)
                self.assertAlmostEqual(result["value"], baseline["value"], places=12)

    def test_observed_radius_works_without_map_level_cs(self):
        rows = extract_rows(orbit(), circle_size=5.2)
        known = measure(rows, circle_size=5.2)
        unspecified = measure(rows, circle_size=None)
        self.assertAlmostEqual(known["value"], unspecified["value"], places=12)

    def test_one_radius_outlier_cannot_establish_its_own_intensity(self):
        rows = extract_rows(orbit(32))
        baseline = measure(rows)
        changed = copy.deepcopy(rows)
        # This is deliberately inconsistent evidence, not a claim that
        # ordinary osu! maps have a per-object CircleSize mechanic. A single
        # anomalous radius must not borrow the entire chain's establishment.
        changed[16]["ls.radius_px"] *= 0.01
        result = measure(changed)
        if result["status"] == "INSUFFICIENT":
            self.assertIsNone(result["value"])
        else:
            self.assertLessEqual(result["value"], baseline["value"] + 1e-9)

    def test_missing_phase_distance_is_not_imputed_as_zero(self):
        rows = extract_rows(orbit())
        for row in rows:
            row["ls.lazy_jump_distance_cs_normalised"] = None
        result = measure(rows)
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertIsNone(result["value"])
        self.assertLess(result["coverage"], 1.0)

    def test_partial_missing_evidence_remains_visible_in_coverage(self):
        rows = extract_rows(orbit(64))
        rows[16]["ls.lazy_jump_distance_cs_normalised"] = None
        result = measure(rows)
        self.assertLess(result["coverage"], 1.0)
        self.assertGreater(result["coverage"], 0.0)
        self.assertGreater(result["value"], 0.0)

    def test_known_zero_movement_is_zero_not_missing_evidence(self):
        result = measure(extract_rows([(256.0, 192.0)] * 33))
        self.assertEqual(result["status"], "FULL")
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["value"], 0.0)

    def test_missing_radius_is_not_invented_from_a_default(self):
        rows = extract_rows(orbit())
        for row in rows:
            row["ls.radius_px"] = None
        result = measure(rows, circle_size=None)
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertIsNone(result["value"])

    def test_finite_extreme_radius_abstains_if_joint_load_is_nonfinite(self):
        rows = extract_rows(orbit())
        radius = 1e-320
        self.assertTrue(math.isfinite(radius) and radius > 0.0)
        for row in rows:
            row["ls.radius_px"] = radius
        # These are finite but unusable low-level signals, not ordinary CS.
        # An unrepresentable joint load is unavailable evidence, not zero.
        result = measure(rows, circle_size=None)
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertIsNone(result["value"])
        self.assertEqual(result["coverage"], 0.0)
        self.assertEqual(result["eligible_count"], 0)
        self.assertGreater(
            result["signals"]["missing_reasons"].get("NONFINITE_EXECUTION_INTENSITY", 0),
            0,
        )

    def test_mirroring_actual_geometry_preserves_flow(self):
        points = orbit(32)
        original = measure(extract_rows(points))
        mirrored = measure(extract_rows([(x, 384.0 - y) for x, y in points]))
        self.assertAlmostEqual(original["value"], mirrored["value"], places=10)
        self.assertAlmostEqual(
            original["winning_section"]["execution_intensity"],
            mirrored["winning_section"]["execution_intensity"],
            places=10,
        )

    def test_generator_supported_and_input_not_mutated(self):
        rows = extract_rows(orbit())
        before = copy.deepcopy(rows)
        ordinary = measure(rows)
        streamed = measure(iter(rows))
        self.assertEqual(rows, before)
        self.assertEqual(ordinary, streamed)


if __name__ == "__main__":
    unittest.main()

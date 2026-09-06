"""Direction, phase, and local-evidence contracts; no human star targets.

Spatial fixtures pass through the actual .osu parser and Local Signal extractor.
Only explicit missing/corrupt-channel tests mutate those extracted rows. The
standalone aggregation tests isolate mathematical and temporal ownership rules.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "tools", ROOT / "src", ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01 import control_vector_v01 as control
from map_demand_v01 import paired_transition_geometry_v01 as paired
from map_demand_v01 import model_v101_experimental as current
from test_flow_execution_v02 import extract_rows
from test_flow_reentry_execution_v01 import actual_slider_rows
from tests.test_map_demand_v01 import mini_calibration
from osu_skill_profiler.parser.osu_parser import parse_osu
from osu_skill_profiler.signals.extractor import LocalSignalExtractor


def points_from_vectors(vectors, repetitions=1):
    points = [(176.0, 112.0)]
    for _ in range(repetitions):
        for dx, dy in vectors:
            points.append((points[-1][0] + dx, points[-1][1] + dy))
    if not all(0 <= x <= 512 and 0 <= y <= 384 for x, y in points):
        raise ValueError("fixture must remain within the osu! playfield")
    return points


def square_points(repetitions=8):
    return points_from_vectors([(80, 0), (0, 80), (-80, 0), (0, -80)], repetitions)


def changed_direction_points():
    return points_from_vectors(
        [(80, 0), (0, 80), (0, -80), (-80, 0),
         (0, 80), (80, 0), (-80, 0), (0, -80)], 4)


def varied_spacing_points():
    return points_from_vectors([(40, 0), (160, 0), (-40, 0), (-160, 0)], 8)


def support(count):
    return -math.expm1(-((count / 3.0) ** 2))


def straight_slider_rows(velocity=2.0, cs=4.0, exit_delay=0.0):
    objects = []
    for x in (0, 50, 100, 450, 500):
        suffix = "2,0,L|150:192,1,50" if x == 100 else "1,0"
        time = 1000 + x / velocity + (exit_delay if x >= 450 else 0)
        objects.append(f"{x},192,{time},{suffix}")
    beatmap = parse_osu(
        "osu file format v14\n[General]\nMode:0\n[Metadata]\nTitle:Uniform path\nArtist:Test\nCreator:Test\nVersion:Test\n"
        f"[Difficulty]\nCircleSize:{cs}\nApproachRate:9\nOverallDifficulty:8\nSliderMultiplier:{velocity*4}\nSliderTickRate:1\n"
        "[TimingPoints]\n0,400,4,2,1,100,1,0\n[HitObjects]\n" + "\n".join(objects))
    rows = LocalSignalExtractor("0.4.0")._extract_rows(beatmap)
    return [{**row, "v091.start_x_px": obj.x, "v091.start_y_px": obj.y}
            for row, obj in zip(rows, beatmap.hit_objects)]


def event(index, effort=1.0, *, interval=100.0, section=0, start_ms=None):
    return {
        "time": (index + 2) * interval,
        "start_ms": index * interval if start_ms is None else start_ms,
        "section": section, "transition_index": index + 1,
        "effort": effort, "scalar_effort": effort,
        "direction_available": True,
    }


class ControlLayerAndLocalEvidenceTests(unittest.TestCase):
    def turning_points(self, turns):
        points = [(0., 0.)]
        heading = 0.
        for turn in turns:
            points.append((points[-1][0]+30*math.cos(heading), points[-1][1]+30*math.sin(heading)))
            heading += math.radians(turn)
        mx = (min(x for x,y in points)+max(x for x,y in points))/2
        my = (min(y for x,y in points)+max(y for x,y in points))/2
        points = [(x+256-mx,y+192-my) for x,y in points]
        self.assertTrue(all(0<=x<=512 and 0<=y<=384 for x,y in points))
        return points

    def test_sharper_angles_and_shorter_times_increase_demand_without_repetition_discount(self):
        for alternating in (False, True):
            values = {}
            for interval in (75., 150.):
                values[interval] = []
                for deflection in (30, 60, 90, 120, 150):
                    turns = [deflection * (-1 if alternating and i%2 else 1) for i in range(16)]
                    m = control.extract_control_measure(extract_rows(self.turning_points(turns), interval=interval))
                    values[interval].append(m['value'])
                    self.assertEqual(m['winning_section']['positive_event_count'], 8)
                self.assertTrue(all(b>a for a,b in zip(values[interval], values[interval][1:])), values)
            self.assertTrue(all(a>b for a,b in zip(values[75.], values[150.])), values)

    def test_more_sharp_turns_in_same_local_time_have_greater_demand(self):
        def value(indices):
            turns = [120 if i in indices else 15 for i in range(16)]
            return control.extract_control_measure(extract_rows(self.turning_points(turns), interval=100))['value']
        # Same number of acute turns, spacing, timing and total map length;
        # one local window contains more acute turns in the clustered case.
        self.assertGreater(value({5,6,7,8}), value({2,6,10,14}))

    def test_empty_and_observed_zero_have_no_effort(self):
        self.assertEqual(control.layer_supported_effort([]), 0.0)
        self.assertEqual(control.layer_supported_effort([0.0] * 8), 0.0)
        self.assertIsNone(control.local_peak([]))

    def test_equal_effort_support_is_bounded_monotone_and_amplitude_linear(self):
        values = [control.layer_supported_effort([2.5] * count) for count in range(1, 9)]
        for count, value in enumerate(values, 1):
            self.assertAlmostEqual(value, 2.5 * support(count), places=13)
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        self.assertLess(values[-1], 2.5)
        self.assertAlmostEqual(control.layer_supported_effort([10, 4, 4]),
                               2 * control.layer_supported_effort([5, 2, 2]), places=13)

    def test_high_effort_layer_cannot_borrow_cheap_context_support(self):
        # The low layer has eight sources; only the spike reaches above it.
        expected = 0.1 * support(8) + (10.0 - 0.1) * support(1)
        actual = control.layer_supported_effort([10.0] + [0.1] * 7)
        self.assertAlmostEqual(actual, expected, places=13)
        self.assertLess(actual, 10.0 * support(2))
        self.assertGreaterEqual(actual, control.layer_supported_effort([10.0]))

    def test_weak_context_limit_is_continuous_not_a_presence_gate(self):
        spike = control.layer_supported_effort([10.0])
        for epsilon in (1e-2, 1e-5, 1e-8, 1e-11):
            actual = control.layer_supported_effort([10.0] + [epsilon] * 7)
            self.assertGreaterEqual(actual, spike)
            self.assertLessEqual(actual - spike, epsilon + 1e-14)

    def test_layer_integral_is_permutation_invariant(self):
        values = [8.0, 0.0, 0.02, 4.0, 4.0, 1.0]
        expected = control.layer_supported_effort(values)
        for ordered in (list(reversed(values)), sorted(values), values[2:] + values[:2]):
            self.assertEqual(control.layer_supported_effort(ordered), expected)

    def test_additional_distant_easy_section_cannot_dilute_or_support_peak(self):
        hard = [event(index, 3.0) for index in range(3)]
        easy = [event(index + 50, 0.01, section=1) for index in range(30)]
        winner = control.local_peak(hard)
        self.assertEqual(control.local_peak(hard + easy), winner)

    def test_eight_opportunity_ceiling_prevents_whole_map_repetition_support(self):
        eight = control.local_peak([event(index) for index in range(8)])
        many = control.local_peak([event(index) for index in range(80)])
        self.assertEqual(eight, many)
        self.assertEqual(many["event_count"], 8)
        self.assertEqual(len(set(many["source_transition_indices"])), 8)

    def test_full_three_circle_source_span_counts_prior_interval(self):
        # End times span only 2400ms for seven events, but their complete
        # source span is 3200ms. Only six complete opportunities fit.
        winner = control.local_peak([event(index, interval=400) for index in range(8)])
        self.assertEqual(winner["event_count"], 6)
        self.assertLessEqual(winner["end_ms"] - winner["start_ms"], 3000.0)
        self.assertAlmostEqual(winner["supported_effort"], support(6), places=13)

    def test_single_opportunity_over_three_seconds_cannot_emit_a_local_peak(self):
        self.assertIsNone(control.local_peak([event(0, interval=1500.01)]))
        self.assertIsNotNone(control.local_peak([event(0, interval=1500.0)]))

    def test_section_boundary_prevents_neighbouring_event_support(self):
        a = [event(0)]
        separate = a + [event(1, section=1)]
        together = a + [event(1)]
        self.assertEqual(control.local_peak(separate)["event_count"], 1)
        self.assertGreater(control.local_peak(together)["value"], control.local_peak(separate)["value"])


class ControlDirectionAndPhaseTests(unittest.TestCase):
    def test_equal_distance_time_different_directions_are_observed(self):
        regular_rows = extract_rows(square_points())
        changed_rows = extract_rows(changed_direction_points())
        bundles = [paired.build_transition_bundle(rows) for rows in (regular_rows, changed_rows)]
        channels = [[transition["channels"][paired.MINIMUM_MINIMUM] for transition in bundle["transitions"]]
                    for bundle in bundles]
        for key in ("distance_px", "time_ms", "velocity_px_per_ms"):
            self.assertEqual([channel[key] for channel in channels[0]],
                             [channel[key] for channel in channels[1]])
        regular, changed = [control.extract_control_measure(rows) for rows in (regular_rows, changed_rows)]
        self.assertEqual(regular["status"], "FULL")
        self.assertEqual(changed["status"], "FULL")
        self.assertEqual(regular["signals"]["scalar_only_same_aggregation"]["value"], 0.0)
        self.assertEqual(changed["signals"]["scalar_only_same_aggregation"]["value"], 0.0)
        self.assertGreater(regular["value"], 0.0)
        self.assertGreater(changed["value"], regular["value"])

    def test_single_turn_sweep_holds_distance_time_and_all_other_terms_fixed(self):
        efforts = []
        for angle in (0.0, math.pi / 6, math.pi / 2, math.pi):
            points = [(170.0, 160.0), (250.0, 160.0),
                      (250.0 + 80 * math.cos(angle), 160.0 + 80 * math.sin(angle))]
            result = control.extract_control_measure(extract_rows(points))
            self.assertEqual(len(result["records"]), 1)
            record = result["records"][0]
            self.assertAlmostEqual(record["spacing_change"], 0.0, places=12)
            self.assertAlmostEqual(record["cadence_change"], 0.0, places=12)
            self.assertAlmostEqual(record["scalar_speed_change"], 0.0, places=12)
            efforts.append(record["effort"])
        self.assertEqual(efforts[0], 0.0)
        self.assertTrue(all(a < b for a, b in zip(efforts, efforts[1:])))

    def test_translation_mirror_and_rigid_rotation_preserve_control(self):
        points = changed_direction_points()
        angle = 0.713
        rotated = [(256 + (x - 256) * math.cos(angle) - (y - 192) * math.sin(angle),
                    192 + (x - 256) * math.sin(angle) + (y - 192) * math.cos(angle)) for x, y in points]
        variants = [[(x + 30, y + 40) for x, y in points],
                    [(512 - x, y) for x, y in points],
                    [(x, 384 - y) for x, y in points], rotated]
        expected = control.extract_control_measure(extract_rows(points))
        for transformed in variants:
            self.assertTrue(all(0 <= x <= 512 and 0 <= y <= 384 for x, y in transformed))
            actual = control.extract_control_measure(extract_rows(transformed))
            self.assertEqual(actual["status"], expected["status"])
            self.assertAlmostEqual(actual["value"], expected["value"], places=10)
            self.assertAlmostEqual(actual["support"], expected["support"], places=10)
            for observed, original in zip(actual["records"], expected["records"]):
                for key in ("effort", "speed_change", "spacing_change", "cadence_change"):
                    self.assertAlmostEqual(observed[key], original[key], places=10)

    def test_collinear_same_direction_exactly_reduces_to_scalar_speed_change(self):
        for d0, d1, t0, t1 in ((40, 80, 100, 100), (80, 40, 100, 100),
                              (40, 80, 100, 200), (40, 80, 150, 70)):
            rows = extract_rows([(100, 192), (100 + d0, 192), (100 + d0 + d1, 192)],
                                intervals=[t0, t1])
            result = control.extract_control_measure(rows)
            record = result["records"][0]
            expected = abs(math.log2((d1 / t1 + 0.12) / (d0 / t0 + 0.12)))
            self.assertAlmostEqual(record["speed_change"], expected, places=12)
            self.assertAlmostEqual(record["speed_change"], record["scalar_speed_change"], places=12)
            self.assertAlmostEqual(record["effort"], record["scalar_effort"], places=12)

    def test_circle_vectors_match_physical_displacement_and_adjusted_time(self):
        rows = extract_rows([(100, 192), (130, 232), (130, 282)], interval=80)
        bundle = paired.build_transition_bundle(rows)
        first = control.full_vector(bundle["transitions"][0], rows)
        self.assertTrue(first["available"])
        self.assertEqual(first["velocity"], [30 / 80, 40 / 80])
        self.assertFalse(first["time_clamped"])

    def test_minimum_time_floor_is_applied_once_and_reported(self):
        rows = extract_rows(square_points(), interval=10)
        bundle = paired.build_transition_bundle(rows)
        for transition in bundle["transitions"]:
            vector = control.full_vector(transition, rows)
            self.assertTrue(vector["available"])
            self.assertTrue(vector["time_clamped"])
            self.assertAlmostEqual(math.hypot(*vector["velocity"]), 80 / 25)
        result = control.extract_control_measure(rows)
        self.assertEqual(result["signals"]["time_clamped_event_count"], len(result["records"]))
        self.assertTrue(all(record["adjustment_time_ms"] == 25 for record in result["records"]))
        at_floor = control.extract_control_measure(extract_rows(square_points(), interval=25))
        self.assertAlmostEqual(result["value"], at_floor["value"], places=12)

    def test_constant_velocity_resampling_does_not_create_spatial_control(self):
        points = [(80, 192), (105, 192), (155, 192), (180, 192), (230, 192)]
        for cs in (4.0, 6.0):
            result = control.extract_control_measure(extract_rows(
                points, intervals=[50, 100, 50, 100], circle_size=cs))
            self.assertEqual(result["status"], "FULL")
            self.assertEqual(result["value"], 0.0)
            self.assertTrue(all(r["cadence_change"] > 0 for r in result["records"]))

    def test_equal_rhythm_ratio_does_not_erase_absolute_adjustment_time(self):
        points = [(100, 192), (140, 192), (230, 252)]
        fast, slow = [control.extract_control_measure(extract_rows(points, intervals=times))
                      for times in ([50, 100], [90, 180])]
        self.assertEqual(fast["records"][0]["cadence_change"], slow["records"][0]["cadence_change"])
        self.assertGreater(fast["value"], slow["value"])

    def test_smaller_targets_raise_control_across_fast_and_relaxed_deadlines(self):
        for interval in (75, 100, 180, 300):
            values = [control.extract_control_measure(extract_rows(
                changed_direction_points(), interval=interval, circle_size=cs))["value"]
                      for cs in (3.0, 4.0, 5.2, 6.0)]
            self.assertTrue(all(a < b for a, b in zip(values, values[1:])), (interval, values))

    def test_missing_or_unrepresentable_radius_cannot_be_default_cs(self):
        for radius in (None, 0.0, 1e-320):
            rows = extract_rows(square_points())
            for row in rows:
                row["ls.radius_px"] = radius
            result = control.extract_control_measure(rows)
            self.assertEqual(result["status"], "INSUFFICIENT")
            self.assertIsNone(result["value"])
            self.assertEqual(result["coverage"], 0.0)

    def test_known_zero_vectors_are_available_and_observed_zero(self):
        rows = extract_rows([(256.0, 192.0)] * 12)
        bundle = paired.build_transition_bundle(rows)
        for transition in bundle["transitions"]:
            vector = control.full_vector(transition, rows)
            self.assertTrue(vector["available"])
            self.assertEqual(vector["velocity"], [0.0, 0.0])
        result = control.extract_control_measure(rows)
        self.assertEqual(result["status"], "FULL")
        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["counterevidence"], 1.0)
        self.assertEqual(result["signals"]["mechanism_coverage"]["direction"], 1.0)

    def test_stop_go_is_known_direction_even_when_inherited_presence_suppresses_it(self):
        result = control.extract_control_measure(extract_rows([(200, 192), (200, 192), (280, 192)]))
        self.assertTrue(result["records"][0]["direction_available"])
        self.assertGreater(result["records"][0]["speed_change"], 0.0)
        self.assertEqual(result["records"][0]["movement_presence"], 0.0)
        self.assertEqual(result["value"], 0.0)
        self.assertTrue(any("stationary stop/go" in item for item in result["signals"]["known_limitations"]))

    def test_missing_direction_with_scalar_zero_cannot_be_observed_zero(self):
        rows = extract_rows(square_points())
        for row in rows:
            row.pop("v091.start_x_px")
        result = control.extract_control_measure(rows)
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertEqual(result["reason"], "UNKNOWN_DIRECTION_IS_NOT_OBSERVED_ZERO")
        self.assertIsNone(result["value"])
        self.assertIsNone(result["counterevidence"])
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["signals"]["mechanism_coverage"]["direction"], 0.0)
        self.assertIn("MISSING_PHASE_POSITION", result["signals"]["direction_missing_reasons"])

    def test_missing_direction_preserves_positive_scalar_observation_only_as_partial(self):
        rows = extract_rows(varied_spacing_points())
        for row in rows:
            row["v091.start_y_px"] = None
        result = control.extract_control_measure(rows)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertGreater(result["value"], 0.0)
        self.assertIsNone(result["counterevidence"])
        self.assertEqual(result["value"], result["signals"]["scalar_only_same_aggregation"]["value"])
        self.assertTrue(all(not record["direction_available"] for record in result["records"]))
        self.assertEqual(result["signals"]["observed_value_scope"], "PARTIAL_OBSERVED_MECHANISMS")

    def test_partial_missing_position_never_has_full_counterevidence(self):
        rows = extract_rows(square_points())
        rows[16]["v091.start_x_px"] = None
        result = control.extract_control_measure(rows)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertGreater(result["value"], 0.0)
        self.assertIsNone(result["counterevidence"])
        self.assertGreater(result["signals"]["mechanism_coverage"]["direction"], 0.0)
        self.assertLess(result["signals"]["mechanism_coverage"]["direction"], 1.0)

    def test_missing_direction_equal_scalar_zero_is_rotation_stable_at_machine_precision(self):
        for angle in (0.0, 0.713, math.pi / 3, math.pi / 2):
            points = [(256+(x-256)*math.cos(angle)-(y-192)*math.sin(angle),
                       192+(x-256)*math.sin(angle)+(y-192)*math.cos(angle)) for x,y in square_points()]
            rows = extract_rows(points)
            for row in rows:
                row["v091.start_x_px"] = None
            result = control.extract_control_measure(rows)
            self.assertEqual(result["status"], "INSUFFICIENT")
            self.assertEqual(result["reason"], "UNKNOWN_DIRECTION_IS_NOT_OBSERVED_ZERO")
            self.assertIsNone(result["value"])
            self.assertIsNone(result["counterevidence"])
            self.assertEqual(result["signals"]["mechanism_coverage"]["direction"], 0.0)

    def test_known_local_peak_is_not_vetoed_by_missing_scalar_context_elsewhere(self):
        rows = extract_rows(changed_direction_points())
        original = control.extract_control_measure(rows)
        for row in rows[16:]:
            row["ls.adjusted_delta_time_ms"] = None
        partial = control.extract_control_measure(rows)
        self.assertLess(partial["coverage"], 0.8)
        self.assertEqual(partial["winning_section"], original["winning_section"])
        self.assertEqual(partial["status"], "DEGRADED")
        self.assertEqual(partial["value"], original["value"])
        self.assertIsNone(partial["counterevidence"])
        self.assertEqual(partial["signals"]["observed_value_scope"], "PARTIAL_OBSERVED_MECHANISMS")

    def test_phase_distance_or_time_mismatch_cannot_reuse_head_vector(self):
        rows = extract_rows(square_points())
        bundle = paired.build_transition_bundle(rows)
        for key, factor in (("distance_px", 0.5), ("time_ms", 2.0)):
            transition = copy.deepcopy(bundle["transitions"][0])
            transition["channels"][paired.FULL_PATH_FULL_TIME][key] *= factor
            result = control.full_vector(transition, rows)
            self.assertFalse(result["available"])
            self.assertEqual(result["reason"], "VECTOR_FULL_PHASE_MISMATCH")
            self.assertIsNone(result["velocity"])

    def test_real_slider_has_scalar_evidence_but_no_invented_direction(self):
        rows = actual_slider_rows(square_points(), slider_at=16)
        bundle = paired.build_transition_bundle(rows)
        adjacent = [transition for transition in bundle["transitions"]
                    if "slider" in (transition["from_kind"], transition["to_kind"])]
        self.assertEqual(len(adjacent), 2)
        for transition in adjacent:
            self.assertTrue(transition["channels"][paired.FULL_PATH_FULL_TIME]["available"])
            vector = control.full_vector(transition, rows)
            self.assertFalse(vector["available"])
            self.assertEqual(vector["reason"], "SLIDER_DIRECTION_PHASE_UNSUPPORTED")
        result = control.extract_control_measure(rows)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertIsNone(result["counterevidence"])
        self.assertGreater(result["value"], 0.0)
        self.assertIn("SLIDER_DIRECTION_PHASE_UNSUPPORTED", result["signals"]["direction_missing_reasons"])
        for record in result["records"]:
            if not record["direction_available"]:
                self.assertEqual(record["effort"], record["scalar_effort"])

    def test_missing_scalar_channel_separates_support_runs(self):
        rows = extract_rows(square_points())
        rows[16]["ls.adjusted_delta_time_ms"] = None
        result = control.extract_control_measure(rows)
        self.assertIn("MISSING_FULL_TIME", result["signals"]["missing_reasons"])
        sections = {record["section"] for record in result["records"]}
        self.assertGreater(len(sections), 1)
        selected = set(result["winning_section"]["source_transition_indices"])
        selected_sections = {record["section"] for record in result["records"]
                             if record["transition_index"] in selected}
        self.assertEqual(len(selected_sections), 1)

    def test_spinner_and_long_rest_isolate_source_sections(self):
        rows = extract_rows(square_points(), spinner_at=16)
        result = control.extract_control_measure(rows)
        self.assertGreater(len({record["section"] for record in result["records"]}), 1)
        intervals = [100.0] * 32
        intervals[16] = 6000.0
        rested = control.extract_control_measure(extract_rows(square_points(), intervals=intervals))
        self.assertGreater(len({record["section"] for record in rested["records"]}), 1)
        self.assertEqual(rested["value"], control.extract_control_measure(extract_rows(square_points()))["value"])
        for record in rested["records"]:
            self.assertLess(record["time"] - record["start_ms"], 3000.0)

    def test_uniform_straight_slider_does_not_invent_speed_changes(self):
        # The forced slider ball and every circle lie on x=v*(t-1000).
        # A constant-speed path is a constructive witness, independent of
        # any beatmap rating or fitting target. Unknown direction stays unknown.
        for velocity in (0.5, 1.0, 2.0):
            for cs in (3.0, 4.0, 6.0):
                rows = straight_slider_rows(velocity, cs)
                self.assertEqual(rows[2]["ls.object_type"], "slider")
                self.assertAlmostEqual(rows[2]["ls.end_time_ms"] - rows[2]["ls.start_time_ms"], 50 / velocity)
                result = control.extract_control_measure(rows)
                self.assertTrue(all(r["scalar_speed_change"] < 1e-12 for r in result["records"]))
                self.assertTrue(all(r["scalar_effort"] == 0 for r in result["records"]))
                self.assertIsNone(result["value"])
                self.assertEqual(result["reason"], "UNKNOWN_DIRECTION_IS_NOT_OBSERVED_ZERO")

    def test_actual_slider_exit_speed_change_remains_positive_partial_evidence(self):
        result = control.extract_control_measure(straight_slider_rows(exit_delay=75))
        self.assertGreater(result["value"], 0.0)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertTrue(any(r["scalar_effort"] > 0 for r in result["records"]))
        self.assertIsNone(result["counterevidence"])

    def test_shortened_minimum_phase_is_not_a_full_phase_dependency(self):
        rows = actual_slider_rows(changed_direction_points(), slider_at=16)
        expected = control.extract_control_measure(rows)
        for row in rows:
            row["ls.minimum_jump_time_ms"] = None
            row["ls.minimum_jump_distance_cs_normalised"] = None
        actual = control.extract_control_measure(rows)
        self.assertEqual(actual["records"], expected["records"])
        self.assertEqual(actual["value"], expected["value"])
        self.assertEqual(actual["coverage"], expected["coverage"])

    def test_empty_short_and_wrong_signal_version_do_not_fabricate_evidence(self):
        for points in ([], [(100, 100)], [(100, 100), (180, 100)]):
            # Empty input exercises the scorer; a valid .osu file itself
            # intentionally requires at least one parsed hit object.
            result = control.extract_control_measure(extract_rows(points) if points else [])
            self.assertEqual(result["status"], "INSUFFICIENT")
            self.assertIsNone(result["value"])
            self.assertIsNone(result["counterevidence"])
        class WrongVersion(list):
            local_signal_version = "incompatible"
        with self.assertRaises(ValueError):
            control.extract_control_measure(WrongVersion(extract_rows(square_points())))


class ControlModPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="control-vector-tests-", dir=ROOT / "tmp")
        cls.path = Path(cls.temp.name) / "direction.osu"
        # File-backed extraction retains the private provenance used by the
        # public pipeline. No row is re-wrapped to evade provenance validation.
        objects = "\n".join(f"{x:.15g},{y:.15g},{1000 + index * 100},1,0"
                            for index, (x, y) in enumerate(changed_direction_points()))
        cls.path.write_text(
            "osu file format v14\n[General]\nMode:0\n"
            "[Metadata]\nTitle:Control causal test\nArtist:Test\nCreator:Test\nVersion:Test\n"
            "[Difficulty]\nCircleSize:4\nApproachRate:9\nOverallDifficulty:8\nHPDrainRate:5\n"
            "SliderMultiplier:1.4\nSliderTickRate:1\n[TimingPoints]\n0,400,4,2,1,100,1,0\n"
            "[HitObjects]\n" + objects + "\n", encoding="utf8")
        cls.extracted = {mods: current.extract_from_path(str(cls.path), mods)
                         for mods in ((), ("DT",), ("HT",), ("HR",), ("HD",), ("EZ",))}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_dt_and_ht_use_actual_transformed_time_once(self):
        measures = {}
        for mods, clock in (((), 1.0), (("DT",), 1.5), (("HT",), 0.75)):
            rows, _, metadata = self.extracted[mods]
            bundle = paired.build_transition_bundle(rows)
            for transition in bundle["transitions"]:
                phase = transition["channels"][paired.FULL_PATH_FULL_TIME]
                self.assertAlmostEqual(phase["time_ms"], 100 / clock, places=9)
                self.assertAlmostEqual(phase["velocity_px_per_ms"], 0.8 * clock, places=9)
            measured = control.extract_control_measure(rows, mods)
            unlabelled = control.extract_control_measure(rows)
            self.assertEqual(measured["value"], unlabelled["value"])
            self.assertEqual(measured["records"], unlabelled["records"])
            measures[mods] = measured
        self.assertGreater(measures[("DT",)]["value"], measures[()]["value"])
        self.assertLess(measures[("HT",)]["value"], measures[()]["value"])

    def test_hidden_is_invariant_and_hr_increase_comes_from_actual_radius(self):
        expected = control.extract_control_measure(self.extracted[()][0])
        hidden = control.extract_control_measure(self.extracted[("HD",)][0], ("HD",))
        self.assertAlmostEqual(hidden["value"], expected["value"], places=10)
        easier = control.extract_control_measure(self.extracted[("EZ",)][0], ("EZ",))
        self.assertLess(easier["value"], expected["value"])
        self.assertEqual(easier["value"], control.extract_control_measure(self.extracted[("EZ",)][0])["value"])
        hr_rows = self.extracted[("HR",)][0]
        harder = control.extract_control_measure(hr_rows, ("HR",))
        self.assertEqual(harder["status"], "FULL")
        self.assertGreater(harder["value"], expected["value"])
        radius_only = copy.deepcopy(self.extracted[()][0])
        for row, hr_row in zip(radius_only, hr_rows):
            row["ls.radius_px"] = hr_row["ls.radius_px"]
        unmirrored = control.extract_control_measure(radius_only)
        self.assertAlmostEqual(harder["value"], unmirrored["value"], places=10)

    def test_current_public_component_uses_the_same_verified_modded_rows(self):
        for mods in ((), ("DT",)):
            rows, features, metadata = self.extracted[mods]
            components, _ = current.extract_components(
                rows, features, metadata["difficulty"],
                clock_rate=metadata["mod_transform_context"]["clock_rate"],
                effective_mods=metadata["mod_context"]["effective_mods"],
                source_local_signal_version=metadata["local_signal_version"])
            raw = components["v101_control_measure"]
            direct = control.extract_control_measure(
                rows, metadata["mod_context"]["effective_mods"],
                resolved_preempt_ms=components.get("reading_preempt_median_ms"))
            self.assertEqual(raw, direct)
            self.assertEqual(raw["status"], "FULL")
            self.assertGreater(raw["value"], 0.0)

    def test_actual_all_slider_scalar_zero_stays_unknown_through_public_analyze(self):
        path = Path(self.temp.name) / "slider-unknown.osu"
        header = self.path.read_text(encoding="utf8").split("[HitObjects]\n")[0]
        # Each short slider starts at the same point. A zero minimum jump
        # says nothing about its unobserved internal/release control direction.
        objects = "\n".join(f"256,192,{1000+index*100},2,0,L|266:192,1,10" for index in range(16))
        path.write_text(header + "[HitObjects]\n" + objects + "\n", encoding="utf8")
        rows, features, metadata = current.extract_from_path(str(path), ())
        self.assertTrue(all(row["ls.object_type"] == "slider" for row in rows))
        components, _ = current.extract_components(
            rows, features, metadata["difficulty"],
            clock_rate=metadata["mod_transform_context"]["clock_rate"],
            effective_mods=metadata["mod_context"]["effective_mods"],
            source_local_signal_version=metadata["local_signal_version"])
        raw = components["v101_control_measure"]
        self.assertEqual(raw["status"], "INSUFFICIENT")
        self.assertIsNone(raw["value"])
        self.assertIsNone(raw["counterevidence"])
        self.assertEqual(raw["signals"]["mechanism_coverage"]["direction"], 0.0)
        output = current.analyze_components(
            checksum=current.sha256_file_bytes(path.read_bytes()), requested_mods=(),
            components=components, calibration=mini_calibration(),
            applied_mod_context=metadata["mod_transform_context"])
        item = output["axes"]["aim_control"]
        self.assertEqual(item["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(item["stars"])
        self.assertIn("V101_INSUFFICIENT_CONTROL_EVIDENCE", item["warnings"])


if __name__ == "__main__":
    unittest.main()

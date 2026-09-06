"""Spatial evidence tests describe geometry, never a map-rating target."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "tools", ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01 import flow_geometry_v02 as geometry
from map_demand_v01 import flow_spatial_reentry_v01 as reentry
from test_flow_geometry_v02 import rows_for, moved
from test_flow_execution_v02 import extract_rows


def points_from_vectors(vectors):
    points = [(100.0, 100.0)]
    for x, y in vectors:
        points.append((points[-1][0] + x, points[-1][1] + y))
    return points


def curved_points(count=7, turn=math.pi / 6, distances=None):
    distances = distances or [30.0] * count
    return points_from_vectors([(distance * math.cos(i * turn), distance * math.sin(i * turn)) for i, distance in enumerate(distances)])


def two_phrases():
    return points_from_vectors([(30, 0), (25, 15), (15, 25), (100, 40), (-10, 30), (-25, 20), (-30, 0)])


def evidence(rows):
    return reentry.extract_spatial_reentry_evidence(geometry.build_flow_geometry(rows))


def bridge_context(result, source_from=3, left=3, right=3):
    event = next(event for event in result["events"] if event["bridge"]["from_source_row_index"] == source_from)
    return next(context for context in event["contexts"] if context["context_id"] == f"L{left}R{right}")


class FlowSpatialReentryEvidenceTests(unittest.TestCase):
    def test_short_six_circle_phrase_requires_no_eight_circle_gate(self):
        points = points_from_vectors([(30, 0), (25, 15), (80, 40), (-10, 30), (-25, 20)])
        result = evidence(extract_rows(points))
        self.assertEqual(len(result["events"]), 1)
        context = bridge_context(result, source_from=2, left=2, right=2)
        self.assertEqual(context["circle_count"], 6)
        self.assertEqual(context["left"]["movement_count"], 2)
        self.assertEqual(len(context["left"]["internal_turns_rad"]), 1)
        self.assertGreater(context["left"]["soft_alignment"], .8)
        self.assertFalse(result["diagnostics"]["frozen_flow_support_used"])

    def test_real_affection_coordinates_provide_modest_gap_and_direction_reset(self):
        # Recorded transformed source objects 944..951 at 150.240..150.904 s.
        # This is a geometric regression fixture, not a whole-map star label.
        points = [(507, 73), (480, 103), (475, 143), (491, 180), (447, 245), (411, 214), (396, 169), (400, 122)]
        context = bridge_context(evidence(extract_rows(points, intervals=[95, 95, 95, 94, 95, 95, 95])))
        self.assertAlmostEqual(context["spatial"]["bridge_distance_px"], math.hypot(44, 65), places=8)
        self.assertGreater(context["spatial"]["chunk_gap_over_larger_side_median"], 1.6)
        self.assertGreater(context["direction"]["average_direction_change_rad"], math.radians(150))
        self.assertGreater(context["direction"]["boundary_turns_rad"][1], math.pi / 2)
        for side in ("left", "right"):
            self.assertGreater(context[side]["soft_alignment"], .8)
        self.assertGreater(context["timing"]["continuity_evidence"], .999)

    def test_candidate_inventory_does_not_claim_classification_or_score(self):
        result = evidence(extract_rows(two_phrases()))
        self.assertFalse(result["diagnostics"]["score_computed"])
        self.assertFalse(result["diagnostics"]["candidates_are_classified_events"])
        self.assertTrue(all(event["classified_as_spatial_reentry"] is None for event in result["events"]))
        self.assertNotIn("value", result)

    def test_confirmed_separation_can_return_near_an_earlier_phrase_point(self):
        # User-confirmed True DJ NM separation, 103.743..104.361 seconds.
        points=[(355,94),(329,23),(254,3),(187,42),(335,245),(367,181),(340,112),(270,95)]
        result=evidence(extract_rows(points,intervals=[88,88,89,88,88,88,89]))
        short=bridge_context(result,source_from=3,left=2,right=2)
        full=bridge_context(result,source_from=3,left=3,right=3)
        self.assertGreater(short['spatial']['gap_excess_ratio'],0.)
        self.assertEqual(full['spatial']['gap_excess_ratio'],0.)
        self.assertGreater(full['spatial']['boundary_step_excess_ratio'],.65)
        self.assertAlmostEqual(short['spatial']['bridge_distance_px'],full['spatial']['bridge_distance_px'])

    def test_uniform_curve_has_no_extra_boundary_change(self):
        result = evidence(extract_rows(curved_points()))
        for event in result["events"]:
            for context in event["contexts"]:
                self.assertEqual(context["direction"]["boundary_turn_excess_rad"], [0.0, 0.0])
                self.assertEqual(context["direction"]["rotation_change_at_boundary"], [0.0, 0.0])
                self.assertEqual(context["direction"]["bridge_rotation_change"], 0.0)
                self.assertEqual(context["spatial"]["gap_excess_ratio"], 0.0)

    def test_variable_spacing_alone_does_not_manufacture_direction_reset(self):
        result = evidence(extract_rows(curved_points(distances=[20, 40, 20, 40, 20, 40, 20])))
        for event in result["events"]:
            for context in event["contexts"]:
                self.assertEqual(context["direction"]["boundary_turn_excess_rad"], [0.0, 0.0])
                self.assertEqual(context["direction"]["rotation_change_at_boundary"], [0.0, 0.0])

    def test_square_jumps_and_reversal_strings_do_not_prove_flow_flanks(self):
        cases = [curved_points(turn=math.pi / 2), [(100 if i % 2 else 180, 190) for i in range(8)]]
        for points in cases:
            with self.subTest(points=points):
                result = evidence(extract_rows(points))
                self.assertGreater(len(result["events"]), 0)
                for event in result["events"]:
                    for context in event["contexts"]:
                        self.assertAlmostEqual(context["left"]["soft_alignment"], 0.0)
                        self.assertAlmostEqual(context["right"]["soft_alignment"], 0.0)

    def test_exact_bridge_reversal_is_reported_without_discarding_independent_flanks(self):
        points = [(60, 190), (80, 190), (100, 190), (120, 190), (400, 190), (380, 190), (360, 190), (340, 190)]
        context = bridge_context(evidence(extract_rows(points)))
        self.assertEqual(context["left"]["soft_alignment"], 1.0)
        self.assertEqual(context["right"]["soft_alignment"], 1.0)
        self.assertEqual(context["direction"]["boundary_turns_rad"], [0.0, math.pi])
        self.assertEqual(context["direction"]["boundary_reversal_continuity"], [1.0, 0.0])

    def test_rhythm_evidence_is_soft_and_exposes_bridge_deadline_change(self):
        baseline = bridge_context(evidence(extract_rows(two_phrases())))
        fractional = bridge_context(evidence(extract_rows(two_phrases(), intervals=[94, 99.1, 97, 101.5, 95, 100, 96])))
        self.assertGreater(fractional["timing"]["continuity_evidence"], .99)
        for bridge_interval in (25.0, 500.0):
            changed = bridge_context(evidence(extract_rows(two_phrases(), intervals=[100] * 3 + [bridge_interval] + [100] * 3)))
            self.assertLess(changed["timing"]["continuity_evidence"], baseline["timing"]["continuity_evidence"])
            self.assertLess(changed["timing"]["bridge_timing_match_evidence"], baseline["timing"]["bridge_timing_match_evidence"])
            self.assertEqual(changed["spatial"], baseline["spatial"])

    def test_globally_slowed_clicks_preserve_rhythm_but_keep_real_time(self):
        baseline = bridge_context(evidence(extract_rows(two_phrases())))
        slower = bridge_context(evidence(extract_rows(two_phrases(), interval=200)))
        self.assertEqual(baseline["timing"]["continuity_evidence"], slower["timing"]["continuity_evidence"])
        self.assertEqual(slower["timing"]["median_interval_ms"], 200)
        self.assertEqual(baseline["spatial"], slower["spatial"])

    def test_slider_anywhere_inside_context_is_excluded(self):
        for slider_at in (2, 3, 4, 5):
            points = two_phrases()
            result = evidence(rows_for(points, sliders={slider_at: (points[slider_at], 0.0, 30.0)}))
            self.assertEqual(result["events"], [])
            self.assertGreater(result["diagnostics"]["excluded_transition_reasons"]["NON_CIRCLE_TRANSITION"], 0)

    def test_source_missing_zero_spinner_and_long_gap_break_runs(self):
        base_points = curved_points(count=20, turn=math.pi / 8)
        cases = {}
        cases["long_gap"] = rows_for(base_points, intervals=[100] * 9 + [2000] + [100] * 10)
        cases["slider"] = rows_for(base_points, sliders={10: (base_points[10], 0.0, 20.0)})
        cases["missing"] = rows_for(base_points)
        cases["missing"][10]["v091.start_x_px"] = None
        cases["spinner"] = rows_for(base_points)
        cases["spinner"][10]["ls.object_type"] = "spinner"
        repeated = list(base_points)
        repeated[10] = repeated[9]
        cases["zero"] = rows_for(repeated)
        for label, rows in cases.items():
            with self.subTest(label=label):
                result = evidence(rows)
                self.assertGreaterEqual(len({event["circle_run_id"] for event in result["events"]}), 2)
                for event in result["events"]:
                    for context in event["contexts"]:
                        self.assertFalse(context["source_index_first"] < 10 < context["source_index_last"])

    def test_alternative_scales_share_exactly_one_bridge_identifier(self):
        result = evidence(rows_for(curved_points(count=12)))
        bridge_ids = [event["bridge_transition_index"] for event in result["events"]]
        self.assertEqual(len(bridge_ids), len(set(bridge_ids)))
        event = next(event for event in result["events"] if event["bridge"]["from_source_row_index"] == 5)
        self.assertEqual(len(event["contexts"]), 9)
        for context in event["contexts"]:
            self.assertEqual(context["left"]["transition_indices"][-1] + 1, event["bridge_transition_index"])
            self.assertEqual(context["right"]["transition_indices"][0] - 1, event["bridge_transition_index"])
            self.assertNotIn(event["bridge_transition_index"], context["left"]["transition_indices"] + context["right"]["transition_indices"])

    def test_rigid_transform_keeps_unsigned_evidence_and_source_ownership(self):
        rows = rows_for(two_phrases())
        baseline = bridge_context(evidence(rows))
        transformed = bridge_context(evidence(moved(rows, rotation=.734, reflection=True, translation=(500, -900))))
        for field in ("bridge_over_larger_side_median", "chunk_gap_over_larger_side_median", "gap_excess_ratio"):
            self.assertAlmostEqual(baseline["spatial"][field], transformed["spatial"][field], places=10)
        for field in ("boundary_turn_excess_rad", "rotation_change_at_boundary", "boundary_reversal_continuity"):
            for first, second in zip(baseline["direction"][field], transformed["direction"][field]):
                self.assertAlmostEqual(first, second, places=10)
        self.assertEqual(baseline["left"]["transition_indices"], transformed["left"]["transition_indices"])

    def test_geometry_bundle_is_unmodified_and_result_is_json_finite(self):
        bundle = geometry.build_flow_geometry(rows_for(two_phrases()))
        before = copy.deepcopy(bundle)
        result = reentry.extract_spatial_reentry_evidence(bundle)
        self.assertEqual(bundle, before)
        json.dumps(result, allow_nan=False)

    def test_wrong_geometry_contract_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Spatial reentry requires"):
            reentry.extract_spatial_reentry_evidence({"schema_version": "legacy", "transitions": []})


if __name__ == "__main__":
    unittest.main()

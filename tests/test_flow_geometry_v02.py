from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import flow_geometry_v02 as flow
from map_demand_v01 import paired_transition_geometry_v01 as paired


def rows_for(points, *, intervals=None, sliders=None):
    """Explicit, phase-consistent rows; slider tuple = (lazy end, travel, time)."""
    intervals = intervals or [100.0] * (len(points) - 1)
    sliders = sliders or {}
    radius = paired.REFERENCE_RADIUS_PX
    scale = 50.0 / radius
    rows = []
    time = 0.0
    for i, head in enumerate(points):
        dt = intervals[i - 1] if i else None
        if i:
            time += dt
        slider = sliders.get(i)
        prior_slider = sliders.get(i - 1)
        origin = prior_slider[0] if prior_slider else points[i - 1] if i else None
        jump = math.dist(origin, head) if origin is not None else None
        rows.append({
            "ls.original_index": i,
            "ls.object_type": "slider" if slider else "circle",
            "ls.start_time_ms": time,
            "ls.end_time_ms": time + (slider[2] if slider else 0.0),
            "ls.radius_px": radius,
            "ls.cs_scale": scale,
            "ls.preempt_ms": 750.0,
            "ls.adjusted_delta_time_ms": dt,
            "ls.jump_distance_raw_px": math.dist(points[i - 1], head) if i else None,
            "ls.lazy_jump_distance_cs_normalised": None if jump is None else jump * scale,
            "ls.minimum_jump_distance_cs_normalised": None if jump is None else jump * scale,
            "ls.minimum_jump_time_ms": dt,
            "ls.lazy_travel_distance_cs_normalised": slider[1] * scale if slider else 0.0,
            "ls.lazy_travel_time_ms": slider[2] if slider else 0.0,
            "ls.lazy_end_position_x_px": slider[0][0] if slider else None,
            "ls.lazy_end_position_y_px": slider[0][1] if slider else None,
            "ls.slider_aware_angle_rad": math.pi if i > 1 else None,
            "v091.start_x_px": head[0],
            "v091.start_y_px": head[1],
        })
    return rows


def moved(rows, rotation=0.0, reflection=False, translation=(0.0, 0.0)):
    result = copy.deepcopy(rows)
    c, s = math.cos(rotation), math.sin(rotation)
    for row in result:
        for xkey, ykey in (
            ("v091.start_x_px", "v091.start_y_px"),
            ("ls.lazy_end_position_x_px", "ls.lazy_end_position_y_px"),
        ):
            if row[xkey] is None:
                continue
            x, y = row[xkey], row[ykey]
            if reflection:
                y = -y
            row[xkey] = c * x - s * y + translation[0]
            row[ykey] = s * x + c * y + translation[1]
    return result


class FlowGeometryV02Tests(unittest.TestCase):
    def test_rigid_invariance_includes_slider_lazy_end_positions(self):
        rows = rows_for(
            [(0.0, 0.0), (80.0, 0.0), (180.0, 60.0), (200.0, 180.0), (80.0, 220.0)],
            intervals=[125.0] * 4,
            sliders={1: ((105.0, 15.0), 40.0, 60.0), 3: ((180.0, 195.0), 30.0, 55.0)},
        )
        original = flow.build_flow_geometry(rows)["transitions"]
        for reflection in (False, True):
            transformed = flow.build_flow_geometry(moved(rows, 0.731, reflection, (539.0, -218.0)))["transitions"]
            for first, second in zip(original, transformed):
                self.assertEqual(first["execution_direction_available"], second["execution_direction_available"])
                self.assertEqual(first["slider_tangent_unavailable"], second["slider_tangent_unavailable"])
                for field in ("turn_angle_rad", "turn_change_rad", "jump_phase_curvature_change_rad_per_px"):
                    if first[field] is None:
                        self.assertIsNone(second[field])
                    else:
                        self.assertAlmostEqual(first[field], second[field], places=10)
                if first["signed_turn_rad"] is not None:
                    self.assertAlmostEqual(second["signed_turn_rad"], first["signed_turn_rad"] * (-1 if reflection else 1))
                self.assertEqual(first["channels"], second["channels"])

    def test_zero_vectors_never_create_a_direction_and_expose_elapsed_gap(self):
        rows = rows_for([(0, 0), (100, 0), (100, 0), (100, 0), (200, 0), (300, 0)], intervals=[100, 80, 120, 90, 100])
        transitions = flow.build_flow_geometry(rows)["transitions"]
        for item in transitions[1:3]:
            self.assertTrue(item["zero_displacement"])
            self.assertFalse(item["execution_direction_available"])
            self.assertIsNone(item["turn_angle_rad"])
        next_motion = transitions[3]
        self.assertTrue(next_motion["execution_direction_available"])
        self.assertEqual(next_motion["zero_gap_count"], 2)
        self.assertEqual(next_motion["direction_span_ms"], 290)
        self.assertEqual(next_motion["turn_angle_rad"], 0.0)
        self.assertEqual(next_motion["direction_reference_transition_index"], 0)

    def test_historical_signed_zero_angle_does_not_leak_into_new_geometry(self):
        rows = rows_for([(235.0, 251.0), (235.0, 251.0), (144.0, 58.0)])
        rows[2]["ls.slider_aware_angle_rad"] = math.pi
        reflected = moved(rows, reflection=True, translation=(0, 384))
        reflected[2]["ls.slider_aware_angle_rad"] = 0.0
        for source in (rows, reflected):
            transition = flow.build_flow_geometry(source)["transitions"][-1]
            self.assertTrue(transition["jump_phase_vector_available"])
            self.assertFalse(transition["execution_direction_available"])
            self.assertIsNone(transition["turn_angle_rad"])
            self.assertEqual(transition["direction_missing_reason"], "NO_PREVIOUS_NONZERO_JUMP_DIRECTION")

    def test_smooth_curvature_and_alternating_bends_are_distinct(self):
        def points_for(headings):
            points = [(0.0, 0.0)]
            for angle in headings:
                x, y = points[-1]
                points.append((x + 80 * math.cos(angle), y + 80 * math.sin(angle)))
            return points
        smooth = flow.build_flow_geometry(rows_for(points_for([0, .3, .6, .9, 1.2, 1.5])))["transitions"]
        alternating = flow.build_flow_geometry(rows_for(points_for([0, .3, 0, .3, 0, .3])))["transitions"]
        self.assertAlmostEqual(smooth[-1]["turn_angle_rad"], alternating[-1]["turn_angle_rad"])
        self.assertLess(max(item["turn_change_rad"] or 0 for item in smooth), 1e-12)
        self.assertAlmostEqual(alternating[-1]["turn_change_rad"], .6)

    def test_exact_reversal_has_known_magnitude_but_no_signed_orientation(self):
        rows = rows_for([(0, 0), (100, 50), (200, 50), (100, 50), (0, 50)])
        for source in (rows, moved(rows, .731, True, (200, 100))):
            reversal = flow.build_flow_geometry(source)["transitions"][2]
            self.assertTrue(reversal["execution_direction_available"])
            self.assertAlmostEqual(reversal["turn_angle_rad"], math.pi)
            self.assertTrue(reversal["signed_turn_ambiguous"])
            self.assertIsNone(reversal["signed_turn_rad"])
            self.assertIsNone(reversal["turn_change_rad"])

    def test_slider_phase_distances_and_times_remain_separate(self):
        rows = rows_for([(0, 0), (120, 0)], intervals=[200], sliders={0: ((60, 0), 80, 150)})
        rows[1]["ls.minimum_jump_distance_cs_normalised"] = 20 * rows[1]["ls.cs_scale"]
        rows[1]["ls.minimum_jump_time_ms"] = 40
        item = flow.build_flow_geometry(rows)["transitions"][0]
        self.assertAlmostEqual(item["channels"][paired.FULL_PATH_FULL_TIME]["distance_px"], 140)
        self.assertEqual(item["channels"][paired.FULL_PATH_FULL_TIME]["time_ms"], 200)
        self.assertAlmostEqual(item["channels"][paired.MINIMUM_MINIMUM]["distance_px"], 20)
        self.assertEqual(item["channels"][paired.MINIMUM_MINIMUM]["time_ms"], 40)
        self.assertAlmostEqual(item["phase_diagnostics"]["remaining_after_lazy_travel_ms"], 50)
        self.assertTrue(item["slider_tangent_unavailable"])
        self.assertFalse(item["phase_diagnostics"]["slider_internal_tangent_reconstructed"])

    def test_slider_travel_with_zero_exit_is_not_a_stationary_bridge(self):
        rows = rows_for([(0, 0), (100, 0), (200, 0), (200, 0), (300, 0)], sliders={2: ((200, 0), 50, 70)})
        items = flow.build_flow_geometry(rows)["transitions"]
        self.assertTrue(items[2]["zero_jump_displacement"])
        self.assertFalse(items[2]["zero_displacement"])
        self.assertEqual(items[2]["direction_missing_reason"], "SLIDER_TRAVEL_WITHOUT_EXIT_DIRECTION")
        self.assertFalse(items[3]["execution_direction_available"])
        self.assertEqual(items[3]["zero_gap_count"], 0)

    def test_missing_or_inconsistent_phase_breaks_history(self):
        for missing_position in (True, False):
            rows = rows_for([(0, 0), (100, 0), (200, 0), (300, 0)], sliders={1: ((100, 0), 0, 60)})
            if missing_position:
                rows[1]["ls.lazy_end_position_x_px"] = None
            else:
                rows[2]["ls.lazy_jump_distance_cs_normalised"] *= .5
            items = flow.build_flow_geometry(rows)["transitions"]
            self.assertFalse(items[1]["execution_direction_available"])
            self.assertFalse(items[2]["execution_direction_available"])
            self.assertEqual(items[2]["direction_missing_reason"], "NO_PREVIOUS_NONZERO_JUMP_DIRECTION")

    def test_long_gap_transition_does_not_lend_direction_to_new_section(self):
        rows = rows_for([(0, 0), (100, 0), (200, 0), (300, 0), (400, 0)], intervals=[100, 2000, 100, 100])
        items = flow.build_flow_geometry(rows)["transitions"]
        self.assertTrue(items[1]["section_start"])
        self.assertFalse(items[2]["execution_direction_available"])
        self.assertTrue(items[3]["execution_direction_available"])

    def test_does_not_mutate_source_or_historical_paired_output(self):
        rows = rows_for([(0, 0), (100, 0), (100, 0), (200, 50)])
        before = copy.deepcopy(rows)
        old_bundle = paired.build_transition_bundle(rows)
        flow.build_flow_geometry(rows)
        self.assertEqual(rows, before)
        self.assertEqual(paired.build_transition_bundle(rows), old_bundle)


if __name__ == "__main__":
    unittest.main()

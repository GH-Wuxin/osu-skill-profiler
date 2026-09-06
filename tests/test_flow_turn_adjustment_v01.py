"""Rotation-change geometry and local-context regressions, without map targets."""
from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from map_demand_v01 import flow_geometry_v02 as geometry  # noqa: E402
from map_demand_v01 import flow_execution_v02 as execution  # noqa: E402
from tests.test_flow_execution_v02 import extract_rows, orbit  # noqa: E402


RATIO = "jump_phase_turn_adjustment_ratio"


def points_with_turns(turns, distance=20.0):
    """Circle-only paths with observed equal distances and explicit heading changes."""
    x, y, heading = 200.0, 190.0, 0.0
    points = [(x, y), (x + distance, y)]
    x += distance
    for turn in turns:
        heading += turn
        x += distance * math.cos(heading)
        y += distance * math.sin(heading)
        points.append((x, y))
    return points


def transitions(points, intervals=None):
    return geometry.build_flow_geometry(
        extract_rows(points, intervals=intervals)
    )["transitions"]


class FlowTurnAdjustmentGeometryTests(unittest.TestCase):
    def test_half_turn_change_is_continuous_on_both_sides_of_pi(self):
        values = []
        for epsilon in (1e-4, 1e-6, 1e-8, 0.0, -1e-8, -1e-6, -1e-4):
            with self.subTest(epsilon=epsilon):
                items = transitions(points_with_turns(
                    [math.pi / 8] * 8 + [math.pi - epsilon] + [math.pi / 8] * 12
                ))
                crossing = min(
                    (i for i, item in enumerate(items) if item["turn_angle_rad"] is not None),
                    key=lambda i: abs(items[i]["turn_angle_rad"] - math.pi),
                )
                ratio = items[crossing + 1][RATIO]
                self.assertIsNotNone(ratio)
                expected = abs(math.sin((math.pi / 8 - (math.pi - epsilon)) / 2))
                self.assertAlmostEqual(ratio, expected, places=10)
                self.assertGreaterEqual(ratio, 0.0)
                self.assertLessEqual(ratio, 1.0)
                if epsilon == 0.0:
                    self.assertTrue(items[crossing]["signed_turn_ambiguous"])
                    self.assertIsNone(items[crossing]["signed_turn_rad"])
                    self.assertIsNone(items[crossing + 1]["turn_change_rad"])
                values.append(ratio)
        self.assertAlmostEqual(values[2], values[3], delta=1e-8)
        self.assertAlmostEqual(values[4], values[3], delta=1e-8)

    def test_constant_curvature_has_no_turn_adjustment(self):
        items = transitions(orbit(24, distance=40.0, turn=math.pi / 4))
        ratios = [item[RATIO] for item in items if item[RATIO] is not None]
        self.assertTrue(ratios)
        self.assertTrue(all(abs(value) <= 1e-10 for value in ratios), ratios)

    def test_alternating_bends_measure_rotation_change_not_unsigned_bend(self):
        points = points_with_turns(
            [math.pi / 4 if i % 2 else -math.pi / 4 for i in range(24)], distance=10.0
        )
        ratios = [item[RATIO] for item in transitions(points) if item[RATIO] is not None]
        self.assertTrue(ratios)
        for ratio in ratios:
            self.assertAlmostEqual(ratio, math.sin(math.pi / 4), places=10)

    def test_rotation_and_reflection_preserve_adjustment_ratio(self):
        points = points_with_turns([
            math.pi / 8, -math.pi / 4, math.pi, math.pi / 8, -math.pi / 6,
        ])
        expected = [item[RATIO] for item in transitions(points)]
        angle = 0.71
        c, s = math.cos(angle), math.sin(angle)
        rotated = [(256 + c * (x - 256) - s * (y - 192),
                    192 + s * (x - 256) + c * (y - 192)) for x, y in points]
        mirrored = [(x, 384 - y) for x, y in points]
        for transformed in (rotated, mirrored):
            actual = [item[RATIO] for item in transitions(transformed)]
            self.assertEqual(len(actual), len(expected))
            for before, after in zip(expected, actual):
                if before is None:
                    self.assertIsNone(after)
                else:
                    self.assertAlmostEqual(before, after, places=10)

    def test_long_gap_resets_rotation_change_history(self):
        points = points_with_turns([math.pi / 4, -math.pi / 4] * 6, distance=10.0)
        intervals = [100.0] * (len(points) - 1)
        intervals[6] = 5000.0
        items = transitions(points, intervals)
        gap = next(i for i, item in enumerate(items) if item["wall_time_ms"] > 1000.0)
        self.assertFalse(items[gap + 1]["execution_direction_available"])
        self.assertIsNone(items[gap + 1][RATIO])
        self.assertTrue(items[gap + 2]["execution_direction_available"])
        self.assertIsNone(items[gap + 2][RATIO])
        self.assertIsNotNone(items[gap + 3][RATIO])

    def test_known_zero_retains_rotation_history_and_elapsed_span(self):
        points = points_with_turns([math.pi / 4, -math.pi / 4] * 5, distance=10.0)
        ordinary = transitions(points)
        with_zero = transitions([*points[:4], points[3], *points[4:]])
        expected = next(item for item in ordinary if item["to_source_row_index"] == 4)
        actual = next(item for item in with_zero if item["to_source_row_index"] == 5)
        self.assertAlmostEqual(actual[RATIO], expected[RATIO], places=10)
        self.assertEqual(actual["zero_gap_count"], 1)
        self.assertEqual(actual["direction_span_ms"], 200.0)

    def test_missing_phase_resets_rotation_history(self):
        points = points_with_turns([math.pi / 4, -math.pi / 4] * 5, distance=10.0)
        rows = extract_rows(points)
        rows[4]["ls.lazy_jump_distance_cs_normalised"] = None
        items = geometry.build_flow_geometry(rows)["transitions"]
        after_missing = {item["to_source_row_index"]: item for item in items}
        self.assertFalse(after_missing[5]["execution_direction_available"])
        self.assertIsNone(after_missing[5][RATIO])
        self.assertTrue(after_missing[6]["execution_direction_available"])
        self.assertIsNone(after_missing[6][RATIO])
        self.assertIsNotNone(after_missing[7][RATIO])


class FlowTurnAdjustmentContextTests(unittest.TestCase):
    def test_external_reversal_cannot_lend_adjustment_to_unchanged_flow_suffix(self):
        suffix = orbit(12, distance=20.0, turn=math.pi / 8)
        ax, ay = suffix[0]
        bx, by = suffix[1]
        dx, dy = bx - ax, by - ay
        baseline = execution.extract_flow_measure(extract_rows(suffix))["value"]
        values = []
        for epsilon in (1e-4, 1e-6, 1e-8, 0.0, -1e-8, -1e-6, -1e-4):
            c, s = math.cos(epsilon), math.sin(epsilon)
            external = (ax + c * dx - s * dy, ay + s * dx + c * dy)
            result = execution.extract_flow_measure(extract_rows([external, *suffix]))
            with self.subTest(epsilon=epsilon):
                self.assertEqual(result["status"], "FULL")
                # Both the movement sequence and its deadlines after the
                # boundary are identical. An external almost-reversal must
                # not introduce a finite control increment into that chain.
                self.assertAlmostEqual(result["value"], baseline, delta=1e-6)
            values.append(result["value"])
        self.assertAlmostEqual(values[2], values[3], delta=1e-8)
        self.assertAlmostEqual(values[4], values[3], delta=1e-8)


if __name__ == "__main__":
    unittest.main()

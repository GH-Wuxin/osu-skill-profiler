from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v010_beta6 as beta6
from map_demand_v01 import paired_transition_geometry_v01 as paired
from map_demand_v01 import spatial_axes_v02 as spatial


RADIUS = spatial.REFERENCE_RADIUS_PX
TARGET_2719427 = Path(
    r"G:\osu! 20210821\Songs\1312124 Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka"
    r"\Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka (Lasse) [Affection].osu"
)
TARGET_764517 = Path(
    r"G:\osu! 20210821\Songs\346339 Three Days Grace - Unbreakable Heart"
    r"\Three Days Grace - Unbreakable Heart (Lumael) [Unbreakable].osu"
)
PRECISION_1111413 = Path(
    r"G:\osu! 20210821\Songs\429436 Kyle Massey - Cory in the House"
    r"\Kyle Massey - Cory in the House (fieryrage) [Expert].osu"
)
PRECISION_ARCHIPELAGO = Path(
    r"G:\osu! 20210821\Songs\1736571 Yu-Peng Chen @HOYO-MiX - A New Summer Adventure!"
    r"\Yu-Peng Chen @HOYO-MiX - A New Summer Adventure! (Mildly Accurate) [Archipelago].osu"
)


def rows_from_steps(
    steps: list[tuple[float, float, float]],
    *,
    radius: float = RADIUS,
    minimum_distances: list[float | None] | None = None,
    kinds: list[str] | None = None,
    travel_distances: list[float | None] | None = None,
) -> list[dict]:
    """Return one initial object followed by the supplied transition steps."""
    count = len(steps) + 1
    scale = 50.0 / radius
    kinds = kinds or ["circle"] * count
    travel_distances = travel_distances or [0.0] * count
    result: list[dict] = []
    time = 0.0
    x = 256.0
    direction = 1.0
    for index in range(count):
        if index == 0:
            distance = None
            interval = None
            angle = None
            minimum = None
        else:
            distance, interval, angle = steps[index - 1]
            time += interval
            direction *= -1.0
            x += direction * min(distance, 500.0)
            minimum = (
                distance
                if minimum_distances is None
                else minimum_distances[index - 1]
            )
        travel = travel_distances[index]
        result.append(
            {
                "ls.original_index": index,
                "ls.object_type": kinds[index],
                "ls.start_time_ms": time,
                "ls.end_time_ms": time,
                "ls.preempt_ms": 750.0,
                "ls.radius_px": radius,
                "ls.cs_scale": scale,
                "ls.adjusted_delta_time_ms": interval,
                "ls.minimum_jump_time_ms": interval,
                "ls.jump_distance_raw_px": distance,
                "ls.minimum_jump_distance_cs_normalised": (
                    None if minimum is None else minimum * scale
                ),
                "ls.lazy_jump_distance_cs_normalised": (
                    None if distance is None else distance * scale
                ),
                "ls.lazy_travel_distance_cs_normalised": (
                    None if travel is None else travel * scale
                ),
                "ls.lazy_travel_time_ms": 0.0,
                "ls.slider_aware_angle_rad": (
                    None if index < 2 else angle
                ),
                "v091.start_x_px": x,
                "v091.start_y_px": 192.0,
            }
        )
    return result


def regular_rows(
    transitions: int,
    *,
    distance: float = 100.0,
    interval: float = 150.0,
    angle: float = math.pi,
    radius: float = RADIUS,
) -> list[dict]:
    return rows_from_steps(
        [(distance, interval, angle)] * transitions,
        radius=radius,
    )


class PairedTransitionContractTests(unittest.TestCase):
    def test_phase_pairs_are_explicit_and_never_cross_mixed(self):
        rows = rows_from_steps(
            [(400.0, 200.0, math.pi)],
            minimum_distances=[80.0],
            kinds=["slider", "circle"],
            travel_distances=[120.0, 0.0],
        )
        rows[1]["ls.minimum_jump_time_ms"] = 50.0
        rows[1]["ls.lazy_jump_distance_cs_normalised"] = (
            100.0 * rows[1]["ls.cs_scale"]
        )
        transition = paired.build_transition_bundle(rows)["transitions"][0]
        channels = transition["channels"]

        self.assertEqual(channels[paired.HEAD_FULL]["distance_px"], 400.0)
        self.assertEqual(channels[paired.HEAD_FULL]["time_ms"], 200.0)
        self.assertAlmostEqual(
            channels[paired.MINIMUM_MINIMUM]["velocity_px_per_ms"],
            80.0 / 50.0,
        )
        self.assertEqual(channels[paired.LAZY_FULL]["distance_px"], 100.0)
        self.assertEqual(
            channels[paired.FULL_PATH_FULL_TIME]["distance_px"],
            220.0,
        )
        self.assertEqual(
            channels[paired.FULL_PATH_FULL_TIME]["time_ms"],
            200.0,
        )

    def test_true_zero_is_available_but_missing_is_not_zero(self):
        zero_rows = rows_from_steps(
            [(0.0, 100.0, 0.0)],
            minimum_distances=[0.0],
        )
        zero = paired.build_transition_bundle(zero_rows)
        zero_channel = zero["transitions"][0]["channels"][paired.MINIMUM_MINIMUM]
        self.assertTrue(zero_channel["available"])
        self.assertEqual(zero_channel["distance_px"], 0.0)
        self.assertEqual(zero_channel["velocity_px_per_ms"], 0.0)
        self.assertEqual(zero_channel["missing_reasons"], [])

        missing_rows = copy.deepcopy(zero_rows)
        missing_rows[1]["ls.minimum_jump_distance_cs_normalised"] = None
        missing = paired.build_transition_bundle(missing_rows)
        missing_channel = missing["transitions"][0]["channels"][paired.MINIMUM_MINIMUM]
        self.assertFalse(missing_channel["available"])
        self.assertIsNone(missing_channel["distance_px"])
        self.assertIn("MISSING_DISTANCE", missing_channel["missing_reasons"])

    def test_spinner_and_post_spinner_are_separators(self):
        rows = regular_rows(4)
        rows[2]["ls.object_type"] = "spinner"
        bundle = paired.build_transition_bundle(rows)

        self.assertEqual(bundle["spinner_count"], 1)
        self.assertEqual(bundle["transition_count"], 2)
        self.assertEqual(len(bundle["objects"]), 4)
        post = next(obj for obj in bundle["objects"] if obj["source_row_index"] == 3)
        self.assertEqual(post["dt"], 0.0)
        self.assertEqual(post["structural_status"], "POST_SPINNER_SEPARATOR")

    def test_equal_time_group_is_structured_and_never_throws(self):
        rows = regular_rows(4)
        rows[2]["ls.start_time_ms"] = rows[1]["ls.start_time_ms"]
        bundle = paired.build_transition_bundle(rows)

        self.assertEqual(bundle["simultaneous_group_count"], 1)
        self.assertEqual(bundle["simultaneous_object_count"], 2)
        self.assertGreater(bundle["ambiguous_transition_count"], 0)
        self.assertEqual(len(paired.predictability(bundle["objects"])), 5)
        output = spatial.extract_spatial_measures(rows)
        for axis in ("jump_aim", "flow_aim", "aim_control", "spatial_precision"):
            self.assertEqual(output[axis]["status"], "INSUFFICIENT")
            self.assertEqual(output[axis]["activation"], 0.0)

    def test_compatibility_objects_keep_reading_and_control_keys(self):
        obj = paired.build_transition_bundle(regular_rows(2))["objects"][1]
        expected = {
            "time", "x", "y", "radius", "preempt", "dt", "segment",
            "distance", "head_distance", "signed_turn", "kind", "free_time",
            "turn", "slider_speed", "end", "phase_channels",
        }
        self.assertTrue(expected.issubset(obj))


class SpatialAvailabilityTests(unittest.TestCase):
    def test_schema_identity_tracks_linked_flow_semantics(self):
        flow = spatial.extract_spatial_measures(regular_rows(20))["flow_aim"]

        self.assertEqual(spatial.SCHEMA_VERSION, "spatial_axes_v0.3.0")
        self.assertEqual(
            flow["scale"],
            "LOCAL_DIRECTIONAL_PATH_COHERENCE_PHYSICAL_LOG_V03",
        )

    def test_full_degraded_and_insufficient_thresholds(self):
        base = regular_rows(20)

        def precision_with_missing(count: int) -> dict:
            rows = copy.deepcopy(base)
            for index in range(1, count + 1):
                rows[index]["ls.minimum_jump_distance_cs_normalised"] = None
            return spatial.extract_spatial_measures(rows)["spatial_precision"]

        full = precision_with_missing(1)
        degraded = precision_with_missing(2)
        insufficient = precision_with_missing(5)

        self.assertEqual(full["coverage"], 0.95)
        self.assertEqual(full["status"], "FULL")
        self.assertEqual(degraded["coverage"], 0.90)
        self.assertEqual(degraded["status"], "DEGRADED")
        self.assertAlmostEqual(degraded["activation"], 0.90)
        self.assertEqual(insufficient["coverage"], 0.75)
        self.assertEqual(insufficient["status"], "INSUFFICIENT")
        self.assertEqual(insufficient["activation"], 0.0)
        self.assertIsNone(insufficient["value"])

    def test_complete_no_flow_is_counterevidence_not_unavailability(self):
        rows = regular_rows(20, distance=100.0, interval=150.0, angle=0.0)
        flow = spatial.extract_spatial_measures(rows)["flow_aim"]

        self.assertEqual(flow["status"], "FULL")
        self.assertEqual(flow["coverage"], 1.0)
        self.assertEqual(flow["activation"], 1.0)
        self.assertEqual(flow["value"], 0.0)
        self.assertEqual(flow["support"], 0.0)
        self.assertEqual(flow["counterevidence"], 1.0)


class SpatialMechanismTests(unittest.TestCase):
    def test_jump_has_no_distance_only_floor(self):
        fast = spatial.extract_spatial_measures(
            regular_rows(9, distance=320.0, interval=100.0)
        )["jump_aim"]
        medium = spatial.extract_spatial_measures(
            regular_rows(9, distance=320.0, interval=1000.0)
        )["jump_aim"]
        slow = spatial.extract_spatial_measures(
            regular_rows(9, distance=320.0, interval=10000.0)
        )["jump_aim"]

        self.assertEqual((fast["status"], medium["status"], slow["status"]),
                         ("FULL", "FULL", "FULL"))
        self.assertGreater(fast["value"], medium["value"] * 2.0)
        self.assertGreater(medium["value"], slow["value"] * 4.0)
        self.assertLess(slow["support"], 0.05)
        self.assertFalse(fast["signals"]["distance_only_floor"])

    def test_local_jump_section_survives_a_thousand_easy_fillers(self):
        hard = [(300.0, 100.0, 0.0)] * 9
        baseline = spatial.extract_spatial_measures(rows_from_steps(hard))["jump_aim"]
        filled = spatial.extract_spatial_measures(
            rows_from_steps(hard + [(5.0, 300.0, 0.0)] * 1000)
        )["jump_aim"]

        self.assertAlmostEqual(filled["value"], baseline["value"], places=12)
        self.assertAlmostEqual(filled["support"], baseline["support"], places=12)
        self.assertEqual(filled["winning_section"]["event_count"], 8)

    def test_zero_strength_fillers_cannot_supply_persistence(self):
        isolated_jump = spatial.extract_spatial_measures(
            rows_from_steps(
                [(500.0, 50.0, 0.0)] + [(0.0, 150.0, 0.0)] * 7
            )
        )["jump_aim"]
        repeated_jump = spatial.extract_spatial_measures(
            regular_rows(8, distance=500.0, interval=50.0, angle=0.0)
        )["jump_aim"]
        self.assertGreater(repeated_jump["value"], isolated_jump["value"])
        self.assertGreater(
            repeated_jump["winning_section"]["effective_events"],
            isolated_jump["winning_section"]["effective_events"],
        )

        isolated_rows = rows_from_steps(
            [(100.0, 100.0, 0.0)] * 10,
            minimum_distances=[250.0, 20.0] + [20.0] * 8,
        )
        repeated_rows = rows_from_steps(
            [(100.0, 100.0, 0.0)] * 10,
            minimum_distances=[250.0, 20.0] * 5,
        )
        isolated = spatial.extract_spatial_measures(isolated_rows)
        repeated = spatial.extract_spatial_measures(repeated_rows)
        for axis in ("aim_control", "spatial_precision"):
            self.assertGreater(repeated[axis]["value"], isolated[axis]["value"])
            self.assertGreater(
                repeated[axis]["winning_section"]["effective_events"],
                isolated[axis]["winning_section"]["effective_events"],
            )

    def test_flow_angle_and_spacing_weights_have_no_audited_cliffs(self):
        for angle in (math.pi / 2.0, 3.0 * math.pi / 4.0):
            at = spatial.extract_spatial_measures(
                regular_rows(20, distance=1.25 * RADIUS, angle=angle)
            )["flow_aim"]
            below = spatial.extract_spatial_measures(
                regular_rows(20, distance=1.25 * RADIUS, angle=angle - 1e-6)
            )["flow_aim"]
            self.assertLess(abs(at["value"] - below["value"]), 1e-4)

        for interval in (220.0, 300.0, 320.0):
            at = spatial.extract_spatial_measures(
                regular_rows(20, distance=1.25 * RADIUS, interval=interval)
            )["flow_aim"]
            after = spatial.extract_spatial_measures(
                regular_rows(20, distance=1.25 * RADIUS, interval=interval + 1e-3)
            )["flow_aim"]
            self.assertLess(abs(at["value"] - after["value"]), 1e-4)

        for spacing in (0.55 * RADIUS, 1.25 * RADIUS):
            at = spatial.extract_spatial_measures(
                regular_rows(20, distance=spacing, angle=math.pi)
            )["flow_aim"]
            below = spatial.extract_spatial_measures(
                regular_rows(20, distance=spacing - 1e-6, angle=math.pi)
            )["flow_aim"]
            self.assertLess(abs(at["value"] - below["value"]), 1e-4)

    def test_flow_turn_tends_continuously_to_zero(self):
        angles = (math.pi / 2.0, 0.10, 0.01, 0.0)
        values = [
            spatial.extract_spatial_measures(
                regular_rows(20, distance=100.0, interval=180.0, angle=angle)
            )["flow_aim"]["value"]
            for angle in angles
        ]

        self.assertGreater(values[0], values[1])
        self.assertGreater(values[1], values[2])
        self.assertGreater(values[2], values[3])
        self.assertEqual(values[3], 0.0)
        self.assertLess(values[2], 0.01)

    def test_flow_requires_adjacent_coherence_not_weak_filler_count(self):
        weak = spatial.extract_spatial_measures(
            regular_rows(
                400,
                distance=100.0,
                interval=250.0,
                angle=math.pi / 5.0,
            )
        )["flow_aim"]

        self.assertEqual(weak["status"], "FULL")
        self.assertEqual(weak["winning_section"]["event_count"], 48)
        self.assertLess(weak["value"], 1.0)
        self.assertLess(weak["winning_section"]["effective_pairs"], 0.25)

    def test_concentrated_path_outranks_equal_weight_diluted_turns(self):
        concentrated_angles = [math.pi] * 8 + [0.0] * 16
        diluted_angles = [math.pi, 0.0, 0.0] * 8

        def measure(angles: list[float]) -> dict:
            steps = [(100.0, 140.0, 0.0)] + [
                (100.0, 140.0, angle) for angle in angles
            ]
            return spatial.extract_spatial_measures(rows_from_steps(steps))["flow_aim"]

        concentrated = measure(concentrated_angles)
        diluted = measure(diluted_angles)

        self.assertAlmostEqual(
            concentrated["winning_section"]["individual_weight_sum"],
            diluted["winning_section"]["individual_weight_sum"],
            places=12,
        )
        self.assertGreater(
            concentrated["winning_section"]["linked_pair_mass"],
            diluted["winning_section"]["linked_pair_mass"],
        )
        self.assertGreater(concentrated["value"], diluted["value"])

    def test_flow_section_cannot_borrow_coherence_across_spinner(self):
        coherent = regular_rows(20, distance=100.0, interval=140.0, angle=math.pi)
        incoherent = regular_rows(60, distance=100.0, interval=140.0, angle=0.0)
        baseline = spatial.extract_spatial_measures(coherent)["flow_aim"]
        combined = copy.deepcopy(coherent)
        spinner_time = combined[-1]["ls.start_time_ms"] + 100.0
        combined.append(
            {
                "ls.object_type": "spinner",
                "ls.start_time_ms": spinner_time,
                "ls.end_time_ms": spinner_time + 1000.0,
            }
        )
        offset = spinner_time + 1200.0
        for row in incoherent:
            moved = copy.deepcopy(row)
            moved["ls.start_time_ms"] += offset
            moved["ls.end_time_ms"] += offset
            combined.append(moved)
        after = spatial.extract_spatial_measures(combined)["flow_aim"]

        self.assertAlmostEqual(after["value"], baseline["value"], places=12)
        self.assertEqual(after["winning_section"]["block"], 0)

    def test_control_and_precision_use_minimum_phase_geometry(self):
        rows = rows_from_steps(
            [(400.0, 100.0, math.pi)] * 12,
            minimum_distances=[0.0] * 12,
        )
        output = spatial.extract_spatial_measures(rows)

        self.assertEqual(output["jump_aim"]["value"], 0.0)
        self.assertEqual(output["aim_control"]["status"], "FULL")
        self.assertEqual(output["aim_control"]["value"], 0.0)
        self.assertEqual(output["spatial_precision"]["status"], "FULL")
        self.assertEqual(output["spatial_precision"]["value"], 0.0)
        self.assertFalse(
            output["aim_control"]["signals"]["head_full_minimum_time_mixing"]
        )

    def test_head_geometry_cannot_change_minimum_phase_control_or_precision(self):
        minimum = [260.0, 28.0, 190.0, 44.0] * 3
        baseline_rows = rows_from_steps(
            [(100.0, 120.0, math.pi)] * len(minimum),
            minimum_distances=minimum,
        )
        changed_rows = copy.deepcopy(baseline_rows)
        for index, row in enumerate(changed_rows[1:], start=1):
            row["ls.jump_distance_raw_px"] = 500.0 if index % 2 else 1.0
            row["ls.slider_aware_angle_rad"] = 0.0 if index % 2 else math.pi
            row["v091.start_x_px"] = float(index * 997 % 512)
            row["v091.start_y_px"] = float(index * 613 % 384)

        baseline = spatial.extract_spatial_measures(baseline_rows)
        changed = spatial.extract_spatial_measures(changed_rows)
        for axis in ("aim_control", "spatial_precision"):
            self.assertEqual(changed[axis]["value"], baseline[axis]["value"])
            self.assertEqual(changed[axis]["support"], baseline[axis]["support"])
            self.assertEqual(
                changed[axis]["winning_section"], baseline[axis]["winning_section"]
            )

    def test_mod_directions_follow_transformed_physics(self):
        nm_rows = regular_rows(20, distance=120.0, interval=150.0, radius=RADIUS)
        hr_rows = regular_rows(
            20, distance=120.0, interval=150.0, radius=RADIUS / 1.30
        )
        ez_rows = regular_rows(
            20, distance=120.0, interval=150.0, radius=RADIUS * 1.30
        )
        dt_rows = regular_rows(20, distance=120.0, interval=112.5, radius=RADIUS)
        nm = spatial.extract_spatial_measures(nm_rows)
        hr = spatial.extract_spatial_measures(hr_rows, effective_mods=("HR",))
        ez = spatial.extract_spatial_measures(ez_rows, effective_mods=("EZ",))
        dt = spatial.extract_spatial_measures(dt_rows, effective_mods=("DT",))

        for axis in ("jump_aim", "flow_aim", "aim_control"):
            self.assertAlmostEqual(hr[axis]["value"], nm[axis]["value"], places=12)
            self.assertAlmostEqual(ez[axis]["value"], nm[axis]["value"], places=12)
        self.assertGreater(hr["spatial_precision"]["value"],
                           nm["spatial_precision"]["value"])
        self.assertLessEqual(ez["spatial_precision"]["value"],
                             nm["spatial_precision"]["value"])
        for axis in ("jump_aim", "flow_aim", "aim_control", "spatial_precision"):
            self.assertGreaterEqual(dt[axis]["value"], nm[axis]["value"])

    def test_legal_extreme_keeps_high_tail_with_closed_evidence(self):
        extreme = spatial.extract_spatial_measures(
            regular_rows(16, distance=500.0, interval=50.0, angle=0.0)
        )["jump_aim"]

        self.assertEqual(extreme["status"], "FULL")
        self.assertGreater(extreme["value"], 10.0)
        self.assertGreater(extreme["support"], 0.95)
        self.assertEqual(extreme["coverage"], 1.0)
        self.assertFalse(extreme["total_sr_used"])
        self.assertGreater(extreme["winning_section"]["joint_load"], 1.0)


@unittest.skipUnless(TARGET_2719427.exists(), "local BID 2719427 source is unavailable")
class Target2719427Tests(unittest.TestCase):
    def test_hdhr_flow_evidence_exceeds_jump_without_total_sr(self):
        rows, _features, _metadata = beta6.extract_from_path(
            str(TARGET_2719427),
            ("HD", "HR"),
        )
        output = spatial.extract_spatial_measures(
            rows,
            effective_mods=("HD", "HR"),
        )

        self.assertEqual(output["jump_aim"]["status"], "FULL")
        self.assertEqual(output["flow_aim"]["status"], "FULL")
        self.assertGreater(
            output["flow_aim"]["value"],
            output["jump_aim"]["value"],
        )
        self.assertEqual(
            max(
                output[axis]["value"]
                for axis in (
                    "jump_aim", "flow_aim", "aim_control", "spatial_precision"
                )
            ),
            output["flow_aim"]["value"],
        )
        self.assertFalse(output["jump_aim"]["total_sr_used"])
        self.assertFalse(output["flow_aim"]["total_sr_used"])
        self.assertGreater(
            output["flow_aim"]["winning_section"]["effective_pairs"],
            8.0,
        )


@unittest.skipUnless(TARGET_764517.exists(), "local BID 764517 source is unavailable")
class Target764517Tests(unittest.TestCase):
    def test_hddt_weak_turn_filler_does_not_accumulate_into_medium_flow(self):
        rows, _features, _metadata = beta6.extract_from_path(
            str(TARGET_764517),
            ("HD", "DT"),
        )
        flow = spatial.extract_spatial_measures(
            rows,
            effective_mods=("HD", "DT"),
        )["flow_aim"]

        self.assertEqual(flow["status"], "FULL")
        self.assertLess(flow["value"], 2.0)
        self.assertLess(flow["winning_section"]["linked_pair_mass"], 0.75)
        self.assertFalse(flow["total_sr_used"])


@unittest.skipUnless(
    TARGET_2719427.exists()
    and PRECISION_1111413.exists()
    and PRECISION_ARCHIPELAGO.exists(),
    "local precision counterexamples are unavailable",
)
class LegitimatePrecisionCounterexamples(unittest.TestCase):
    def test_small_circle_precision_tail_survives_without_stream_speed_leakage(self):
        cory_rows, _features, _metadata = beta6.extract_from_path(
            str(PRECISION_1111413)
        )
        archipelago_rows, _features, _metadata = beta6.extract_from_path(
            str(PRECISION_ARCHIPELAGO)
        )
        target_rows, _features, _metadata = beta6.extract_from_path(
            str(TARGET_2719427),
            ("HD", "HR"),
        )
        cory = spatial.extract_spatial_measures(cory_rows)
        archipelago = spatial.extract_spatial_measures(archipelago_rows)
        target = spatial.extract_spatial_measures(
            target_rows,
            effective_mods=("HD", "HR"),
        )

        self.assertGreater(cory["spatial_precision"]["value"], 4.8)
        self.assertGreater(archipelago["spatial_precision"]["value"], 8.5)
        self.assertGreater(
            cory["spatial_precision"]["value"],
            target["spatial_precision"]["value"],
        )
        self.assertGreater(
            archipelago["spatial_precision"]["winning_section"]
            ["mean_target_tightness_octaves"],
            1.5,
        )
        self.assertEqual(
            max(
                archipelago[axis]["value"]
                for axis in (
                    "jump_aim", "flow_aim", "aim_control", "spatial_precision"
                )
            ),
            archipelago["spatial_precision"]["value"],
        )


if __name__ == "__main__":
    unittest.main()

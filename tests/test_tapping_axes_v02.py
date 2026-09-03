from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from map_demand_v01 import tapping_axes_v02 as tapping


def rows_for(
    intervals: list[float],
    *,
    start_ms: float = 0.0,
    path_distance: float = 0.0,
    adjusted: list[float] | None = None,
) -> list[dict]:
    rows = [
        {
            "ls.object_type": "circle",
            "ls.start_time_ms": start_ms,
            "ls.end_time_ms": start_ms,
            "ls.delta_time_ms": None,
            "ls.adjusted_delta_time_ms": None,
            "ls.double_tap_feasibility": 0.0,
            "ls.lazy_travel_distance_cs_normalised": 0.0,
        }
    ]
    time_ms = start_ms
    for index, interval in enumerate(intervals):
        time_ms += interval
        rows.append(
            {
                "ls.object_type": "circle",
                "ls.start_time_ms": time_ms,
                "ls.end_time_ms": time_ms,
                "ls.delta_time_ms": interval,
                "ls.adjusted_delta_time_ms": (
                    max(interval, 25.0) if adjusted is None else adjusted[index]
                ),
                "ls.double_tap_feasibility": 0.0,
                "ls.lazy_travel_distance_cs_normalised": 0.0,
                "ls.lazy_jump_distance_cs_normalised": path_distance,
                # Deliberately incoherent legacy pair: the v02 motion channel
                # must ignore both fields in favour of full path / full time.
                "ls.jump_distance_raw_px": 999.0,
                "ls.minimum_jump_time_ms": 1.0,
                "ls.slider_aware_angle_rad": math.pi,
            }
        )
    return rows


def append_spinner_block(
    first: list[dict],
    intervals: list[float],
    *,
    gap_ms: float = 2000.0,
    path_distance: float = 0.0,
) -> list[dict]:
    rows = [dict(row) for row in first]
    time_ms = float(rows[-1]["ls.start_time_ms"])
    half_gap = gap_ms / 2.0
    time_ms += half_gap
    rows.append(
        {
            "ls.object_type": "spinner",
            "ls.start_time_ms": time_ms,
            "ls.end_time_ms": time_ms,
            "ls.delta_time_ms": half_gap,
            "ls.adjusted_delta_time_ms": max(half_gap, 25.0),
            "ls.double_tap_feasibility": 0.0,
            "ls.lazy_travel_distance_cs_normalised": 0.0,
        }
    )
    time_ms += half_gap
    rows.append(
        {
            "ls.object_type": "circle",
            "ls.start_time_ms": time_ms,
            "ls.end_time_ms": time_ms,
            "ls.delta_time_ms": half_gap,
            "ls.adjusted_delta_time_ms": max(half_gap, 25.0),
            "ls.double_tap_feasibility": 0.0,
            "ls.lazy_travel_distance_cs_normalised": 0.0,
            "ls.lazy_jump_distance_cs_normalised": 0.0,
        }
    )
    for interval in intervals:
        time_ms += interval
        rows.append(
            {
                "ls.object_type": "circle",
                "ls.start_time_ms": time_ms,
                "ls.end_time_ms": time_ms,
                "ls.delta_time_ms": interval,
                "ls.adjusted_delta_time_ms": max(interval, 25.0),
                "ls.double_tap_feasibility": 0.0,
                "ls.lazy_travel_distance_cs_normalised": 0.0,
                "ls.lazy_jump_distance_cs_normalised": path_distance,
                "ls.jump_distance_raw_px": 999.0,
                "ls.minimum_jump_time_ms": 1.0,
                "ls.slider_aware_angle_rad": math.pi,
            }
        )
    return rows


def measure(rows: list[dict], axis: str) -> dict:
    return tapping.extract_tapping_measures(rows)[axis]


class EventBundleTests(unittest.TestCase):
    def test_schema_identity_tracks_post_preliminary_tapping_repairs(self):
        bundle = tapping.build_event_bundle(rows_for([100.0, 100.0]))
        self.assertEqual(tapping.SCHEMA_VERSION, "tapping_axes_v0.3.0")
        self.assertEqual(bundle["schema_version"], tapping.SCHEMA_VERSION)
        self.assertEqual(bundle["version"], tapping.SCHEMA_VERSION)

    def test_wall_and_execution_clocks_are_distinct_without_missing_zero_conflation(self):
        rows = rows_for([1.0, 80.0])
        bundle = tapping.build_event_bundle(rows)
        self.assertEqual(bundle["events"][0]["wall_dt_ms"], 1.0)
        self.assertEqual(bundle["events"][0]["execution_dt_ms"], 25.0)
        self.assertTrue(bundle["events"][0]["tap_valid"])
        self.assertEqual(bundle["coverage"]["tap_execution"]["status"], "FULL")

        missing = tapping.build_event_bundle(rows + [{"ls.object_type": "circle"}])
        self.assertIsNone(missing["events"][-1]["wall_dt_ms"])
        self.assertFalse(missing["events"][-1]["tap_valid"])
        self.assertIn(
            "tap_wall_delta_missing_or_negative",
            missing["coverage"]["tap_execution"]["missing_reasons"],
        )

    def test_spinner_and_post_spinner_never_form_a_pair(self):
        rows = rows_for([])
        time_ms = 0.0
        for index in range(20):
            time_ms += 100.0
            kind = "spinner" if index % 2 == 0 else "circle"
            rows.append(
                {
                    "ls.object_type": kind,
                    "ls.start_time_ms": time_ms,
                    "ls.end_time_ms": time_ms,
                    "ls.delta_time_ms": 100.0,
                    "ls.adjusted_delta_time_ms": 100.0,
                    "ls.lazy_travel_distance_cs_normalised": 0.0,
                    "ls.lazy_jump_distance_cs_normalised": 300.0,
                }
            )
        bundle = tapping.build_event_bundle(rows)
        self.assertEqual(bundle["coverage"]["tap_execution"]["candidate_count"], 0)
        for result in tapping.extract_tapping_measures(rows).values():
            self.assertEqual(result["status"], "INSUFFICIENT")
            self.assertEqual(result["value"], 0.0)
            self.assertEqual(result["evidence_count"], 0)

    def test_simultaneous_group_and_its_boundaries_are_isolated(self):
        # The two objects at 100 ms have no unique temporal order.  Neither
        # the incoming edge, the within-group file-order edge, nor the outgoing
        # edge may become tapping evidence.  The later singleton pair remains.
        rows = rows_for([100.0, 0.0, 100.0, 50.0])
        bundle = tapping.build_event_bundle(rows)
        self.assertEqual(bundle["timeline"]["simultaneous_group_count"], 1)
        self.assertEqual(bundle["timeline"]["simultaneous_object_count"], 2)
        self.assertEqual(len(bundle["events"]), 1)
        self.assertEqual(bundle["events"][0]["previous_start_ms"], 200.0)
        self.assertEqual(bundle["events"][0]["start_ms"], 250.0)
        self.assertEqual(bundle["events"][0]["execution_dt_ms"], 50.0)
        reasons = {
            item["reason"] for item in bundle["timeline"]["separator_intervals"]
        }
        self.assertEqual(
            reasons,
            {
                "current_simultaneous_group",
                "within_simultaneous_group",
                "post_simultaneous_group",
            },
        )

    def test_repeated_simultaneous_doublets_do_not_form_a_raw_speed_run(self):
        rows = rows_for([0.0, 120.0] * 8)
        bundle = tapping.build_event_bundle(rows)
        self.assertEqual(bundle["timeline"]["simultaneous_group_count"], 8)
        self.assertEqual(bundle["coverage"]["tap_execution"]["candidate_count"], 0)
        result = tapping.extract_tapping_measures(rows)["raw_speed"]
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertEqual(result["value"], 0.0)

    def test_positive_sub_floor_interval_remains_ordered_adjusted_evidence(self):
        rows = rows_for([1.0, 80.0, 1.0])
        bundle = tapping.build_event_bundle(rows)
        self.assertEqual(bundle["timeline"]["simultaneous_group_count"], 0)
        self.assertEqual([event["wall_dt_ms"] for event in bundle["events"]], [1.0, 80.0, 1.0])
        self.assertEqual(
            [event["execution_dt_ms"] for event in bundle["events"]],
            [25.0, 80.0, 25.0],
        )

    def test_input_rows_are_not_mutated(self):
        rows = rows_for([75.0] * 30)
        before = copy.deepcopy(rows)
        tapping.build_event_bundle(rows)
        tapping.extract_tapping_measures(rows)
        self.assertEqual(rows, before)


class RawSpeedTests(unittest.TestCase):
    def test_raw_speed_identity_is_v03_without_changing_its_value_path(self):
        result = measure(rows_for([50.0] * 8), "raw_speed")
        self.assertEqual(result["signals"]["scale"], "INDEPENDENT_PHYSICAL_RATE_V03")

    def test_rate_length_and_repetition_cannot_be_borrowed_across_runs(self):
        slow = rows_for([175.0] * 30)
        burst = rows_for([25.0] * 4)
        union = append_spinner_block(slow, [25.0] * 4)
        slow_value = measure(slow, "raw_speed")["value"]
        burst_value = measure(burst, "raw_speed")["value"]
        combined = measure(union, "raw_speed")
        self.assertAlmostEqual(combined["value"], max(slow_value, burst_value))
        self.assertEqual(combined["winning_run"]["observed_pairs"], 4)
        self.assertGreater(combined["winning_run"]["rate_per_s"], 35.0)

    def test_single_interval_does_not_establish_raw_speed(self):
        result = measure(rows_for([25.0]), "raw_speed")
        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["activation"], 0.0)

    def test_cadence_uses_adjusted_not_raw_delta(self):
        raw_one = rows_for([84.0, 1.0] * 20)
        raw_twenty_five = rows_for([84.0, 25.0] * 20)
        a = tapping.extract_tapping_measures(raw_one)
        b = tapping.extract_tapping_measures(raw_twenty_five)
        self.assertAlmostEqual(a["raw_speed"]["value"], b["raw_speed"]["value"])
        self.assertAlmostEqual(
            a["raw_speed"]["winning_run"]["rate_per_s"],
            b["raw_speed"]["winning_run"]["rate_per_s"],
        )
        self.assertAlmostEqual(a["finger_control"]["value"], b["finger_control"]["value"])
        # Stamina correctly retains real elapsed time rather than inventing
        # 25 ms of wall-clock sustain for each simultaneous object.
        self.assertLess(a["stamina"]["value"], b["stamina"]["value"])

    def test_double_tap_feasibility_reduces_raw_evidence_in_the_same_run(self):
        clean = rows_for([40.0] * 24)
        cheesable = copy.deepcopy(clean)
        for row in cheesable[1:]:
            row["ls.double_tap_feasibility"] = 0.75

        clean_result = measure(clean, "raw_speed")
        cheese_result = measure(cheesable, "raw_speed")
        self.assertLess(cheese_result["value"], clean_result["value"])
        self.assertEqual(cheese_result["coverage"]["channels"]["double_tap"]["status"], "FULL")
        self.assertAlmostEqual(
            cheese_result["winning_run"]["double_tap_feasibility_mean"],
            0.75,
        )
        self.assertLess(
            cheese_result["winning_run"]["effective_pairs"],
            cheese_result["winning_run"]["opportunity_pairs"],
        )

    def test_missing_double_tap_evidence_cannot_pose_as_zero_feasibility(self):
        rows = rows_for([40.0] * 20)
        for row in rows[1:7]:
            row.pop("ls.double_tap_feasibility")
        result = measure(rows, "raw_speed")
        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertEqual(result["value"], 0.0)
        channel = result["coverage"]["channels"]["double_tap"]
        self.assertLess(channel["ratio"], tapping.DEGRADED_COVERAGE)
        self.assertIn(
            "double_tap_feasibility_missing_or_nonfinite",
            channel["missing_reasons"],
        )


class StaminaTests(unittest.TestCase):
    def test_far_slow_filler_does_not_amplify_fast_winning_run(self):
        burst = rows_for([50.0] * 20)
        cut = 1000.0 / 6.0 * 1.015
        below = append_spinner_block(rows_for([cut - 1e-6] * 1000), [50.0] * 20)
        above = append_spinner_block(rows_for([cut + 1e-6] * 1000), [50.0] * 20)
        expected = measure(burst, "stamina")
        low = measure(below, "stamina")
        high = measure(above, "stamina")
        self.assertAlmostEqual(low["value"], expected["value"])
        self.assertAlmostEqual(high["value"], expected["value"])
        self.assertAlmostEqual(low["value"], high["value"])
        self.assertEqual(low["winning_run"]["observed_pairs"], 20)

    def test_speed_and_duration_are_bound_to_same_run(self):
        short_fast = rows_for([31.25] * 6)
        long_moderate = rows_for([100.0] * 200)
        union = append_spinner_block(long_moderate, [31.25] * 6)
        result = measure(union, "stamina")
        alternatives = [measure(short_fast, "stamina"), measure(long_moderate, "stamina")]
        self.assertLessEqual(result["value"], max(item["value"] for item in alternatives) + 1e-12)


class FingerControlTests(unittest.TestCase):
    def test_uniform_speed_baseline_cannot_be_donated_to_rhythm_window(self):
        uniform = rows_for([25.0] * 100)
        rhythm = rows_for([120.0, 240.0] * 12)
        union = append_spinner_block(uniform, [120.0, 240.0] * 12)
        self.assertEqual(measure(uniform, "finger_control")["value"], 0.0)
        expected = measure(rhythm, "finger_control")
        combined = measure(union, "finger_control")
        self.assertAlmostEqual(combined["value"], expected["value"])
        self.assertAlmostEqual(
            combined["winning_window"]["local_baseline"],
            expected["winning_window"]["local_baseline"],
        )

    def test_old_cadence_tolerance_boundary_is_continuous(self):
        boundary = 2.0**0.08
        below = rows_for([100.0, 100.0 * (boundary - 1e-8)] * 100)
        above = rows_for([100.0, 100.0 * (boundary + 1e-8)] * 100)
        a = measure(below, "finger_control")["value"]
        b = measure(above, "finger_control")["value"]
        self.assertLess(abs(a - b), 1e-3)


class EnduranceTests(unittest.TestCase):
    def test_full_coverage_cannot_create_duration_free_endurance_floor(self):
        one_pair = measure(rows_for([25.0]), "endurance")
        seven_pairs = measure(rows_for([25.0] * 7), "endurance")
        self.assertEqual(one_pair["status"], "FULL")
        self.assertLess(one_pair["value"], 0.05)
        self.assertLess(seven_pairs["value"], 0.2)
        self.assertLess(one_pair["activation"], seven_pairs["activation"])

    def test_motion_uses_full_path_over_full_wall_time_only(self):
        stationary = rows_for([1000.0] * 200, path_distance=0.0)
        moving = rows_for([1000.0] * 200, path_distance=300.0)
        stationary_value = measure(stationary, "endurance")["value"]
        moving_result = measure(moving, "endurance")
        self.assertGreater(moving_result["value"], stationary_value + 0.25)
        self.assertTrue(moving_result["signals"]["motion_channel_used"])

        changed_legacy_pair = copy.deepcopy(moving)
        for row in changed_legacy_pair[1:]:
            row["ls.jump_distance_raw_px"] = 1_000_000.0
            row["ls.minimum_jump_time_ms"] = 0.001
        self.assertEqual(measure(changed_legacy_pair, "endurance"), moving_result)

    def test_missing_padding_lowers_coverage_instead_of_looking_like_rest(self):
        base = rows_for([75.0] * 40)
        padded = base + [{"ls.object_type": "circle"} for _ in range(1000)]
        for axis, result in tapping.extract_tapping_measures(padded).items():
            with self.subTest(axis=axis):
                self.assertEqual(result["status"], "INSUFFICIENT")
                self.assertEqual(result["value"], 0.0)
                self.assertLess(result["coverage"]["ratio"], 0.1)
                self.assertEqual(result["counterevidence"], 0.0)


class MeasureEnvelopeTests(unittest.TestCase):
    def test_every_measure_has_replayable_envelope_and_no_total_sr(self):
        measures = tapping.extract_tapping_measures(rows_for([80.0, 120.0, 160.0] * 30))
        json.dumps(measures, allow_nan=False)
        self.assertEqual(
            set(measures), {"raw_speed", "stamina", "finger_control", "endurance"}
        )
        required = {
            "schema_version",
            "status",
            "value",
            "support",
            "counterevidence",
            "activation",
            "evidence_count",
            "coverage",
            "winning_run",
            "winning_window",
            "total_sr_used",
            "signals",
        }
        for axis, result in measures.items():
            with self.subTest(axis=axis):
                self.assertTrue(required.issubset(result))
                self.assertEqual(result["schema_version"], tapping.SCHEMA_VERSION)
                self.assertFalse(result["total_sr_used"])
                self.assertIn(result["status"], {"FULL", "DEGRADED", "INSUFFICIENT"})
                self.assertTrue(math.isfinite(result["value"]))

    def test_legitimate_synthetic_extremes_retain_mechanism_evidence(self):
        raw = measure(rows_for([67.0] * 64), "raw_speed")
        stamina = measure(rows_for([31.25] * 38), "stamina")
        finger = measure(
            rows_for(([61.0, 94.0, 137.0, 77.0, 188.0, 111.0] * 8)),
            "finger_control",
        )
        endurance = measure(rows_for([100.0] * 3000), "endurance")
        self.assertGreater(raw["value"], 7.0)
        self.assertGreater(raw["winning_run"]["effective_pairs"], 50.0)
        self.assertGreater(stamina["value"], 8.0)
        self.assertGreater(stamina["winning_run"]["rate_per_s"], 25.0)
        self.assertGreater(finger["evidence_count"], 30)
        self.assertGreater(finger["activation"], 0.9)
        self.assertGreater(endurance["value"], 5.0)
        self.assertGreater(endurance["signals"]["effective_duration_s"], 250.0)


RUN_CORPUS = os.environ.get("OSU_SKILL_RUN_CORPUS_TESTS") == "1"
SONGS = Path(r"G:\osu! 20210821\Songs")


@unittest.skipUnless(RUN_CORPUS and SONGS.is_dir(), "set OSU_SKILL_RUN_CORPUS_TESTS=1")
class OptionalRealExtremeTests(unittest.TestCase):
    @staticmethod
    def _rows(set_id: int, name_fragment: str) -> list[dict]:
        from map_demand_v01 import model_v010_beta5

        directories = list(SONGS.glob(f"{set_id} *"))
        if not directories:
            raise AssertionError(f"missing beatmap set {set_id}")
        paths = [path for path in directories[0].glob("*.osu") if name_fragment in path.name]
        if len(paths) != 1:
            raise AssertionError(f"expected one {set_id}/{name_fragment}, got {paths}")
        rows, _, _ = model_v010_beta5.extract_from_path(str(paths[0]))
        return rows

    def test_named_extremes_keep_same_axis_mechanism_provenance(self):
        settia = measure(self._rows(1495669, "Epilogue"), "raw_speed")
        chuj = measure(self._rows(488602, "Chujother"), "stamina")
        vektor = measure(self._rows(489236, "Cygnus Terminal"), "finger_control")
        seselis = measure(self._rows(997827, "Aspire"), "finger_control")
        helfro = measure(self._rows(1440921, "Kedjur Innri"), "endurance")

        self.assertGreater(settia["winning_run"]["rate_per_s"], 12.0)
        self.assertGreater(settia["winning_run"]["observed_pairs"], 30)
        self.assertGreater(chuj["winning_run"]["rate_per_s"], 20.0)
        self.assertGreater(chuj["winning_run"]["observed_pairs"], 20)
        self.assertGreater(vektor["evidence_count"], 100)
        self.assertGreater(seselis["evidence_count"], 100)
        self.assertGreater(helfro["signals"]["effective_duration_s"], 100.0)
        self.assertGreater(helfro["signals"]["longest_continuous_effective_s"], 10.0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import tapping_axes_v02 as previous  # noqa: E402
from map_demand_v01 import tapping_axes_v03 as tapping  # noqa: E402


def rows_for(
    intervals: list[float],
    *,
    start_ms: float = 0.0,
    double_tap_feasibility: float = 0.0,
) -> list[dict]:
    rows = [
        {
            "ls.object_type": "circle",
            "ls.start_time_ms": start_ms,
            "ls.end_time_ms": start_ms,
            "ls.delta_time_ms": None,
            "ls.adjusted_delta_time_ms": None,
            "ls.double_tap_feasibility": double_tap_feasibility,
            "ls.lazy_travel_distance_cs_normalised": 0.0,
        }
    ]
    time_ms = start_ms
    for interval in intervals:
        time_ms += interval
        rows.append(
            {
                "ls.object_type": "circle",
                "ls.start_time_ms": time_ms,
                "ls.end_time_ms": time_ms,
                "ls.delta_time_ms": interval,
                "ls.adjusted_delta_time_ms": max(interval, 25.0),
                "ls.double_tap_feasibility": double_tap_feasibility,
                "ls.lazy_travel_distance_cs_normalised": 0.0,
                "ls.lazy_jump_distance_cs_normalised": 0.0,
                "ls.slider_aware_angle_rad": math.pi,
            }
        )
    return rows


def append_spinner_block(
    first: list[dict],
    intervals: list[float],
    *,
    gap_ms: float = 2000.0,
    double_tap_feasibility: float = 0.0,
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
            "ls.double_tap_feasibility": double_tap_feasibility,
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
                "ls.double_tap_feasibility": double_tap_feasibility,
                "ls.lazy_travel_distance_cs_normalised": 0.0,
                "ls.lazy_jump_distance_cs_normalised": 0.0,
                "ls.slider_aware_angle_rad": math.pi,
            }
        )
    return rows


def raw(rows: list[dict]) -> dict:
    return tapping.extract_tapping_measures(rows)["raw_speed"]


def measure(rows: list[dict], axis: str) -> dict:
    return tapping.extract_tapping_measures(rows)[axis]


class RawSpeedFrontierTests(unittest.TestCase):
    def test_schema_and_public_value_identify_the_explicit_raw_selector(self):
        result = raw(rows_for([40.0] * 20))

        self.assertEqual(tapping.SCHEMA_VERSION, "tapping_axes_v0.5.0")
        self.assertEqual(result["schema_version"], tapping.SCHEMA_VERSION)
        self.assertEqual(
            result["signals"]["frontier_engine"],
            "axis_support_frontier_v01",
        )
        self.assertEqual(
            result["signals"]["public_value_policy"],
            "SELECTED_SUPPORT_FRONTIER_STAR",
        )
        self.assertEqual(
            result["value"], result["public_frontier"]["frontier_star"]
        )
        self.assertNotIn(
            "recurrence", result["public_frontier"]["eligible_components"]
        )
        self.assertLessEqual(result["value"], result["physical_peak"])
        self.assertTrue(result["signals"]["confidence_not_applied_to_value"])

    def test_six_pair_burst_and_long_stream_keep_the_same_peak_but_not_support(self):
        burst = raw(rows_for([40.0] * 6))
        stream = raw(rows_for([40.0] * 60))

        self.assertAlmostEqual(burst["physical_peak"], stream["physical_peak"])
        self.assertAlmostEqual(
            burst["signals"]["physical_peak_rate_per_s"],
            stream["signals"]["physical_peak_rate_per_s"],
        )
        self.assertLess(burst["value"], burst["physical_peak"])
        self.assertGreater(stream["value"], burst["value"] * 1.20)
        self.assertGreater(
            stream["establishment"]["support"],
            burst["establishment"]["support"],
        )
        self.assertGreater(
            stream["sustain"]["frontier_star"],
            burst["sustain"]["frontier_star"] + 5.0,
        )

    def test_extending_one_high_speed_episode_raises_establishment_and_sustain(self):
        short = raw(rows_for([50.0] * 4))
        medium = raw(rows_for([50.0] * 6))
        long = raw(rows_for([50.0] * 20))

        self.assertAlmostEqual(short["physical_peak"], medium["physical_peak"])
        self.assertAlmostEqual(medium["physical_peak"], long["physical_peak"])
        self.assertLess(short["value"], medium["value"])
        self.assertLess(medium["value"], long["value"])
        self.assertLess(
            short["sustain"]["frontier_star"],
            medium["sustain"]["frontier_star"],
        )
        self.assertLess(
            medium["sustain"]["frontier_star"],
            long["sustain"]["frontier_star"],
        )

    def test_separated_repetitions_raise_recurrence_not_episode_establishment(self):
        single_rows = rows_for([40.0] * 6)
        repeated_rows = append_spinner_block(single_rows, [40.0] * 6)
        repeated_rows = append_spinner_block(repeated_rows, [40.0] * 6)
        single = raw(single_rows)
        repeated = raw(repeated_rows)

        self.assertAlmostEqual(single["physical_peak"], repeated["physical_peak"])
        self.assertAlmostEqual(single["value"], repeated["value"])
        self.assertEqual(single["recurrence"]["frontier_star"], 0.0)
        self.assertGreater(repeated["recurrence"]["support"], 0.9)
        self.assertGreater(
            repeated["recurrence"]["frontier_star"],
            single["recurrence"]["frontier_star"],
        )
        self.assertGreaterEqual(repeated["recurrence"]["episode_count"], 3)

    def test_arbitrarily_many_slow_fillers_do_not_dilute_the_hard_frontier(self):
        burst_rows = rows_for([40.0] * 12)
        padded_rows = append_spinner_block(rows_for([300.0] * 1000), [40.0] * 12)
        burst = raw(burst_rows)
        padded = raw(padded_rows)

        self.assertAlmostEqual(padded["physical_peak"], burst["physical_peak"])
        self.assertAlmostEqual(padded["value"], burst["value"])
        self.assertAlmostEqual(
            padded["establishment"]["frontier_star"],
            burst["establishment"]["frontier_star"],
        )
        self.assertAlmostEqual(
            padded["sustain"]["frontier_star"],
            burst["sustain"]["frontier_star"],
        )

    def test_evidence_confidence_is_metadata_and_never_multiplies_a_frontier(self):
        samples = [
            {
                "difficulty": 14.0,
                "time_ms": index * 40.0,
                "duration_ms": 40.0,
                "episode_id": 1,
                "section_id": 0,
                "weight": 1.0,
            }
            for index in range(20)
        ]
        low = tapping._frontier(samples, evidence_confidence=0.21)  # noqa: SLF001
        high = tapping._frontier(samples, evidence_confidence=0.97)  # noqa: SLF001

        self.assertEqual(low["physical_peak"], high["physical_peak"])
        for name in ("establishment", "sustain", "recurrence"):
            self.assertEqual(low[name], high[name])
        self.assertEqual(low["combined_frontier_star"], high["combined_frontier_star"])
        self.assertEqual(low["evidence_confidence"], 0.21)
        self.assertEqual(high["evidence_confidence"], 0.97)

        complete_rows = rows_for([40.0] * 20)
        incomplete_rows = complete_rows + [
            {"ls.object_type": "circle"} for _ in range(100)
        ]
        complete = raw(complete_rows)
        incomplete = raw(incomplete_rows)
        self.assertEqual(incomplete["status"], "INSUFFICIENT")
        self.assertLess(
            incomplete["evidence_confidence"],
            complete["evidence_confidence"],
        )
        self.assertEqual(incomplete["physical_peak"], complete["physical_peak"])
        self.assertEqual(incomplete["value"], complete["value"])
        self.assertEqual(incomplete["counterevidence"], 0.0)

    def test_legal_extreme_peak_and_established_value_are_not_clipped_at_ten(self):
        result = raw(rows_for([25.0] * 80))

        expected_peak = (40.0 - tapping.RAW_RATE_BASELINE_PER_S) / tapping.RAW_RATE_PER_STAR
        self.assertAlmostEqual(result["physical_peak"], expected_peak)
        self.assertGreater(result["physical_peak"], 10.0)
        self.assertGreater(result["value"], 10.0)
        self.assertEqual(result["value"], result["physical_peak"])
        self.assertTrue(math.isfinite(result["value"]))

    def test_double_tap_weight_changes_establishment_but_not_physical_peak(self):
        clean = raw(rows_for([40.0] * 20, double_tap_feasibility=0.0))
        cheesable = raw(rows_for([40.0] * 20, double_tap_feasibility=0.75))

        self.assertEqual(clean["physical_peak"], cheesable["physical_peak"])
        self.assertLess(cheesable["value"], clean["value"])
        self.assertLess(
            cheesable["establishment"]["support"],
            clean["establishment"]["support"],
        )
        self.assertEqual(clean["evidence_confidence"], cheesable["evidence_confidence"])

    def test_zero_positive_mechanism_weight_abstains_instead_of_crashing(self):
        result = raw(
            rows_for([40.0] * 20, double_tap_feasibility=1.0)
        )

        self.assertEqual(result["status"], "INSUFFICIENT")
        self.assertEqual(
            result["reason"],
            "NO_POSITIVE_RAW_SPEED_MECHANISM_EVIDENCE",
        )
        self.assertGreater(result["physical_peak"], 10.0)
        self.assertEqual(result["establishment"]["frontier_star"], 0.0)
        self.assertEqual(result["value"], 0.0)

    def test_frontier_schema_mismatch_fails_closed(self):
        samples = [
            {
                "difficulty": 4.0,
                "time_ms": 0.0,
                "duration_ms": 50.0,
                "episode_id": 0,
                "section_id": 0,
                "weight": 1.0,
            }
        ]
        with mock.patch.object(
            tapping,
            "evaluate_support_frontier",
            return_value={"schema_version": "future_incompatible_schema"},
        ):
            with self.assertRaisesRegex(ValueError, "schema mismatch"):
                tapping._frontier(samples, evidence_confidence=1.0)  # noqa: SLF001


class DoubleTapAwareStaminaTests(unittest.TestCase):
    @staticmethod
    def _stacked_double_rhythm(repetitions: int = 48) -> list[dict]:
        rows = rows_for([13.0, 197.0] * repetitions)
        for row in rows[1:]:
            row["ls.double_tap_feasibility"] = (
                0.93 if row["ls.delta_time_ms"] < 25.0 else 0.0
            )
        return rows

    def test_cheesable_stacked_double_mass_does_not_pose_as_stamina(self):
        rows = self._stacked_double_rhythm()
        old = previous.extract_tapping_measures(rows)["stamina"]
        new = measure(rows, "stamina")

        self.assertLess(new["value"], old["value"] * 0.60)
        self.assertEqual(new["signals"]["scale"], "BOUNDED_0_10")
        self.assertEqual(
            new["signals"]["double_tap_weight_policy"],
            tapping.STAMINA_DOUBLE_TAP_WEIGHT_POLICY,
        )
        self.assertLess(
            new["winning_run"]["effective_pairs"],
            new["winning_run"]["opportunity_pairs"],
        )
        self.assertLessEqual(new["value"], 10.0)

    def test_non_cheesable_stamina_retains_the_frozen_bounded_value(self):
        rows = rows_for([62.5] * 96, double_tap_feasibility=0.0)
        old = previous.extract_tapping_measures(rows)["stamina"]
        new = measure(rows, "stamina")

        self.assertEqual(new["value"], old["value"])
        self.assertEqual(new["winning_run"]["rate_per_s"], 16.0)
        self.assertEqual(
            new["winning_run"]["effective_pairs"],
            new["winning_run"]["opportunity_pairs"],
        )


class DoubleTapAwareFingerControlTests(unittest.TestCase):
    @staticmethod
    def _stacked_double_rhythm(repetitions: int = 48) -> list[dict]:
        rows = rows_for([13.0, 197.0] * repetitions)
        for row in rows[1:]:
            row["ls.double_tap_feasibility"] = (
                0.93 if row["ls.delta_time_ms"] < 25.0 else 0.0
            )
        return rows

    def test_both_contrasts_around_a_stacked_double_receive_relief(self):
        rows = self._stacked_double_rhythm()
        old = previous.extract_tapping_measures(rows)["finger_control"]
        new = measure(rows, "finger_control")

        self.assertLess(new["value"], old["value"] * 0.40)
        self.assertEqual(
            new["signals"]["double_tap_weight_policy"],
            tapping.FINGER_DOUBLE_TAP_WEIGHT_POLICY,
        )
        self.assertGreater(
            new["winning_window"]["double_tap_relief_mean"],
            0.90,
        )
        self.assertLess(
            new["winning_window"]["effective_transition_weight"],
            new["winning_window"]["transition_count"] * 0.10,
        )

    def test_non_cheesable_extreme_is_unchanged_and_not_hard_capped(self):
        rows = rows_for(
            [25.0, 100.0] * 100,
            double_tap_feasibility=0.0,
        )
        old = previous.extract_tapping_measures(rows)["finger_control"]
        new = measure(rows, "finger_control")

        self.assertEqual(new["value"], old["value"])
        self.assertGreater(new["value"], 10.0)
        self.assertEqual(
            new["winning_window"]["effective_transition_weight"],
            float(new["winning_window"]["transition_count"]),
        )

    def test_missing_double_tap_signal_abstains_instead_of_becoming_zero_relief(self):
        rows = rows_for([80.0, 120.0, 160.0] * 30)
        for row in rows[1:80]:
            row.pop("ls.double_tap_feasibility")

        for axis in ("stamina", "finger_control"):
            with self.subTest(axis=axis):
                result = measure(rows, axis)
                self.assertEqual(result["status"], "INSUFFICIENT")
                self.assertEqual(result["value"], 0.0)
                self.assertIn(
                    "double_tap_feasibility_missing_or_nonfinite",
                    result["coverage"]["channels"]["double_tap"][
                        "missing_reasons"
                    ],
                )


class DelegatedAxesTests(unittest.TestCase):
    def test_endurance_delegates_v02_unchanged(self):
        rows = rows_for([80.0, 120.0, 160.0, 95.0] * 30)
        old = previous.extract_tapping_measures(rows)
        new = tapping.extract_tapping_measures(rows)

        actual = dict(new["endurance"])
        self.assertEqual(
            actual.pop("implementation_basis_schema_version"),
            previous.SCHEMA_VERSION,
        )
        actual["schema_version"] = previous.SCHEMA_VERSION
        self.assertEqual(actual, old["endurance"])

    def test_output_is_finite_serialisable_and_does_not_mutate_input(self):
        rows = rows_for([25.0] * 80)
        before = copy.deepcopy(rows)
        output = tapping.extract_tapping_measures(rows)

        json.dumps(output, allow_nan=False)
        self.assertEqual(rows, before)
        self.assertEqual(
            set(output),
            {"raw_speed", "stamina", "finger_control", "endurance"},
        )
        for measure in output.values():
            self.assertEqual(measure["schema_version"], tapping.SCHEMA_VERSION)
            self.assertFalse(measure["total_sr_used"])


RUN_CORPUS = os.environ.get("OSU_SKILL_RUN_CORPUS_TESTS") == "1"
SONGS = Path(r"G:\osu! 20210821\Songs")


@unittest.skipUnless(
    RUN_CORPUS and SONGS.is_dir(),
    "set OSU_SKILL_RUN_CORPUS_TESTS=1",
)
class OptionalRealDoubleTapRegressionTests(unittest.TestCase):
    @staticmethod
    def _rows(set_id: int, name_fragment: str) -> list[dict]:
        from map_demand_v01 import model_v010_beta7

        directories = list(SONGS.glob(f"{set_id} *"))
        if len(directories) != 1:
            raise AssertionError(f"expected one set {set_id}, got {directories}")
        paths = [
            path
            for path in directories[0].glob("*.osu")
            if name_fragment in path.name
        ]
        if len(paths) != 1:
            raise AssertionError(
                f"expected one {set_id}/{name_fragment}, got {paths}"
            )
        rows, _, _ = model_v010_beta7.extract_from_path(str(paths[0]))
        return rows

    def test_fakens_stacked_doubles_no_longer_dominate_stamina_or_finger(self):
        rows = self._rows(1551322, "FAKEN'S CHALLENGE")
        old = previous.extract_tapping_measures(rows)
        new = tapping.extract_tapping_measures(rows)

        self.assertGreater(old["finger_control"]["value"], 14.0)
        self.assertLess(new["finger_control"]["value"], 6.0)
        self.assertGreater(old["stamina"]["value"], 8.0)
        self.assertLess(new["stamina"]["value"], 4.0)
        self.assertGreater(
            old["finger_control"]["value"],
            new["finger_control"]["value"] * 2.0,
        )

    def test_legitimate_sustained_extremes_are_preserved(self):
        kurukuru = self._rows(1235834, "kurukuru")
        nordlys = self._rows(1999022, "Heimdallr av Bivrost")
        yolo = self._rows(710630, "YOLO")

        old_kuru = previous.extract_tapping_measures(kurukuru)["finger_control"]
        new_kuru = measure(kurukuru, "finger_control")
        self.assertEqual(new_kuru["value"], old_kuru["value"])
        self.assertGreater(new_kuru["value"], 8.0)

        old_nordlys = previous.extract_tapping_measures(nordlys)["stamina"]
        new_nordlys = measure(nordlys, "stamina")
        self.assertEqual(new_nordlys["value"], old_nordlys["value"])
        self.assertGreater(new_nordlys["value"], 6.5)

        old_yolo = previous.extract_tapping_measures(yolo)["stamina"]
        new_yolo = measure(yolo, "stamina")
        self.assertLess(abs(new_yolo["value"] - old_yolo["value"]), 0.02)
        self.assertGreater(new_yolo["value"], 9.0)


if __name__ == "__main__":
    unittest.main()

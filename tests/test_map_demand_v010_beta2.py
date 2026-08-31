from __future__ import annotations

import copy
import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from map_demand_v01 import model_v010_beta2 as beta
from map_demand_v01 import model_v010_beta1 as previous
from map_demand_v01 import contract as C
from map_demand_v01 import release
from tests.test_map_demand_v01 import mini_calibration


def rows_for(intervals, cs=4, distance=120):
    radius = (54.4 - 4.48 * cs) * 1.00041
    rows = [{"ls.object_type": "circle", "ls.start_time_ms": 0,
             "ls.radius_px": radius}]
    time = 0
    for dt in intervals:
        time += dt
        rows.append({"ls.object_type": "circle", "ls.start_time_ms": time,
                     "ls.end_time_ms": time, "ls.delta_time_ms": dt,
                     "ls.adjusted_delta_time_ms": dt, "ls.radius_px": radius,
                     "ls.jump_distance_raw_px": distance,
                     "ls.slider_aware_angle_rad": math.pi})
    return rows


def measure(intervals, axis, **kwargs):
    return getattr(beta, axis + "_measure")(beta._events(rows_for(intervals, **kwargs)))


class StaminaTests(unittest.TestCase):
    def test_seven_note_entry_is_gradual_not_full_scale(self):
        values = [measure([1000 / 14] * (n - 1), "stamina")["value"] for n in (6, 7, 10, 25, 200)]
        self.assertEqual(values[0], 0)
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        self.assertLess(values[1], 1.5)
        self.assertGreater(values[-1], 7)

    def test_same_two_hundred_notes_have_superlinear_rate_pressure(self):
        reports = [measure([15000 / bpm] * 199, "stamina") for bpm in (180, 210, 240)]
        self.assertLess(reports[0]["value"], reports[1]["value"])
        self.assertLess(reports[1]["value"], reports[2]["value"])
        self.assertGreater(reports[2]["rate_pressure"] - reports[1]["rate_pressure"],
                           reports[1]["rate_pressure"] - reports[0]["rate_pressure"])

    def test_short_fast_pairs_cannot_lend_speed_to_long_slow_chain(self):
        slow = [15000 / 150] * 199
        alone = measure(slow, "stamina")
        mixed = measure(slow + [2000] + [50, 50, 500] * 30, "stamina")
        self.assertEqual(alone["value"], mixed["value"])
        self.assertEqual(mixed["notes"], 200)
        self.assertAlmostEqual(mixed["rate_per_s"], 10)

    def test_half_rate_recovery_is_not_a_fast_chain(self):
        mixed = measure(([70] * 4 + [140] * 4) * 20, "stamina")
        sustained = measure([70] * 160, "stamina")
        self.assertLess(mixed["rate_per_s"], 11)
        self.assertLess(mixed["value"], sustained["value"] - 2)

    def test_real_duration_matches_winning_chain(self):
        result = measure(([96] * 4 + [144] * 2) * 30, "stamina")
        self.assertAlmostEqual(result["duration_s"], (result["end_ms"] - result["start_ms"]) / 1000)
        self.assertAlmostEqual(result["rate_per_s"] * result["duration_s"], result["notes"] - 1)

    def test_repetition_adds_bounded_support_and_filler_does_not_dilute(self):
        chain = [75] * 24
        one = measure(chain, "stamina")["value"]
        repeated = measure((chain + [2000]) * 20, "stamina")["value"]
        filler = measure(chain + [1000] * 500, "stamina")["value"]
        self.assertGreater(repeated, one)
        self.assertLess(repeated, one * 1.3)
        self.assertEqual(filler, one)


class PrecisionTests(unittest.TestCase):
    def test_fixed_geometry_is_strictly_monotonic_in_cs_including_above_eight(self):
        values = [measure([150] * 100, "precision", cs=cs)["value"] for cs in range(11)]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])), values)
        self.assertGreater(values[7], values[4] * 2)
        self.assertLess(values[2], values[4] * .8)

    def test_shrinking_target_does_not_remove_micro_evidence(self):
        values = []
        micro = []
        for cs in (3, 4, 5, 6, 7, 8, 9):
            rows = rows_for([150] * 50, cs=cs)
            for i, row in enumerate(rows):
                row["ls.jump_distance_raw_px"] = 300 if i % 2 else 40
                row["ls.slider_aware_angle_rad"] = .3
            result = beta.precision_measure(beta._events(rows))
            values.append(result["value"])
            micro.append(result["micro_peak"])
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        self.assertGreater(micro[0], 0)
        self.assertEqual(len(set(micro)), 1)

    def test_large_jump_does_not_turn_precision_into_jump_again(self):
        near = measure([150] * 100, "precision", distance=100)["value"]
        far = measure([150] * 100, "precision", distance=400)["value"]
        self.assertLess(far, near * 1.1)
        self.assertEqual(measure([150] * 100, "precision", cs=9, distance=0)["value"], 0)

    def test_small_target_with_slow_acquisitions_still_matters(self):
        small = measure([600] * 100, "precision", cs=7)["value"]
        big = measure([80] * 100, "precision", cs=3)["value"]
        self.assertGreater(small, big)


class FingerTests(unittest.TestCase):
    def test_periodic_swing_is_less_demanding_than_unpredictable_groups(self):
        periodic = [144, 96] * 100
        shuffled = periodic.copy()
        random.Random(12).shuffle(shuffled)
        regular = measure(periodic, "finger")["value"]
        irregular = measure(shuffled, "finger")["value"]
        self.assertGreater(irregular, regular * 1.2)

    def test_same_pattern_scales_with_execution_speed(self):
        values = [measure([dt, dt / 2] * 100, "finger")["value"] for dt in (300, 200, 100)]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))

    def test_no_250ms_cliff(self):
        a = measure([249, 124.5] * 50, "finger")["value"]
        b = measure([251, 125.5] * 50, "finger")["value"]
        self.assertGreater(b, 1)
        self.assertLess(abs(a - b), .15)

    def test_uniform_high_speed_is_not_extreme_finger_control(self):
        self.assertLess(measure([50] * 300, "finger")["value"], 1.5)

    def test_group_length_and_parity_transitions_are_observed(self):
        intervals = sum(([100] * (i % 5 + 2) + [200] * (i % 3 + 1) for i in range(60)), [])
        result = measure(intervals, "finger")
        self.assertGreater(result["parity_changes"], 30)
        self.assertGreater(result["value"], measure([100, 200] * 180, "finger")["value"])

    def test_short_difficult_section_not_erased_by_easy_filler(self):
        difficult = random.Random(8).choices([48, 72, 96, 144, 192, 288], k=100)
        before = measure(difficult, "finger")["value"]
        after = measure([500] * 500 + [2000] + difficult + [2000] + [500] * 500, "finger")["value"]
        self.assertAlmostEqual(before, after)

    def test_long_gaps_do_not_create_high_control(self):
        self.assertLess(measure([100, 4000] * 80, "finger")["value"], 1)

    def test_omitted_pulses_are_not_new_cadences(self):
        # Same local 80ms pulse, irregular omissions, no exact repeated motif.
        intervals = [80 * n for n in random.Random(7).choices([1, 2, 3, 4], k=200)]
        groups = beta._cadence_groups(beta._events(rows_for(intervals)))
        self.assertAlmostEqual(beta._pulse_predictability(groups, 20), .8)

    def test_unobserved_common_divisor_is_not_invented(self):
        intervals = [96, 144] * 60
        groups = beta._cadence_groups(beta._events(rows_for(intervals)))
        # 48ms is not a demonstrated tapping pulse. Repetition may make this
        # particular swing predictable, but it cannot certify a 48ms grid.
        self.assertLess(beta._pulse_predictability(groups, 20), .1)

    def test_baseline_tutorial_pace_cannot_be_fast_control(self):
        intervals = random.Random(1).choices([500, 750, 1000], k=100)
        self.assertLess(measure(intervals, "finger")["value"], 1.5)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.rows = rows_for(([100] * 8 + [180] * 3) * 12)
        self.calibration = mini_calibration()
        self.components, _ = beta.extract_components(self.rows)
        self.args = dict(checksum="sha256:" + "b" * 64, components=self.components,
                         calibration=self.calibration)

    def test_identity_changes_but_other_six_axes_are_exactly_unchanged(self):
        before = previous.analyze_components(**self.args)
        after = beta.analyze_components(**self.args)
        self.assertNotEqual(C.identity_cache_key(before["identity"]), C.identity_cache_key(after["identity"]))
        self.assertEqual(after["release"]["stage"], "PUBLIC_BETA")
        for axis in C.AXIS_ORDER:
            if axis not in beta.CHANGED_AXES:
                self.assertEqual(before["axes"][axis], after["axes"][axis], axis)
        C.scan_finite(after, "test.beta2")

    def test_three_axes_do_not_use_total_sr(self):
        results = []
        for stars in (1, 5, 12):
            self.components["v091_nm_star_anchor"] = stars
            results.append(beta.analyze_components(**self.args)["axes"])
        for axis in beta.CHANGED_AXES:
            self.assertEqual(len({r[axis]["demand_star_equivalent"] for r in results}), 1, axis)

    def test_extraction_and_analysis_leave_input_untouched(self):
        rows_before = copy.deepcopy(self.rows)
        beta.extract_components(self.rows)
        self.assertEqual(self.rows, rows_before)
        components_before = copy.deepcopy(self.components)
        beta.analyze_components(**self.args)
        self.assertEqual(self.components, components_before)

    def test_old_components_are_not_silently_accepted(self):
        self.components.pop("beta2_measures")
        with self.assertRaisesRegex(ValueError, "own local component extraction"):
            beta.analyze_components(**self.args)

    def test_runtime_supports_beta2_and_preserves_beta1_rollback(self):
        self.assertIs(release.runtime_model("v010-beta2"), beta)
        self.assertIs(release.runtime_model("v010-beta1"), previous)

    def test_spinner_does_not_donate_a_tap_to_seven_note_threshold(self):
        rows = rows_for([70] * 6)
        rows[0]["ls.object_type"] = "spinner"
        self.assertEqual(beta.stamina_measure(beta._events(rows))["value"], 0)

    def test_real_elapsed_time_not_legacy_minimum_delta(self):
        rows = rows_for([20] * 20)
        for row in rows[1:]:
            row["ls.adjusted_delta_time_ms"] = 25
        result = beta.stamina_measure(beta._events(rows))
        self.assertAlmostEqual(result["duration_s"], .4)
        self.assertAlmostEqual(result["rate_per_s"], 50)

    def test_mapper_bpm_metadata_cannot_change_three_axes(self):
        a, _ = beta.extract_components(self.rows, {"bpm": 200})
        b, _ = beta.extract_components(self.rows, {"bpm": 400})
        self.assertEqual(a["beta2_measures"], b["beta2_measures"])


class PublicBeta2WorkbenchTests(unittest.TestCase):
    from tests.test_bid_review_ui_v01 import BidReviewWorkbenchTests as _fixtures
    setUp = _fixtures.setUp
    tearDown = _fixtures.tearDown

    def test_mod_analysis_feedback_and_cache_identity(self):
        import json
        from map_demand_v01.bid_review_ui_v01 import BidReviewWorkbench
        args = dict(manifest_path=self.manifest, songs_root=self.songs,
                    calibration_path=self.calibration, responses_path=self.responses,
                    reviewer_id="tester", cache_root=self.cache)
        current = BidReviewWorkbench(**args, algorithm="v010-beta2")
        old = BidReviewWorkbench(**args, algorithm="v010-beta1")
        for mods in ([], ["HD"], ["HD", "DT"]):
            with self.subTest(mods=mods):
                result = current.analyze_bid(123456, requested_mods=mods)
                self.assertEqual(result["status"], "OK")
                self.assertEqual(result["identity"]["map_demand_version"], "0.10.0-beta.2")
                self.assertEqual(result["release"]["stage"], "PUBLIC_BETA")
                self.assertEqual(result["identity"]["calibration_id"], current.state()["calibration_id"])
                self.assertNotEqual(result["analysis_id"], old.analyze_bid(123456, requested_mods=mods)["analysis_id"])
                self.assertEqual(len(result["axes"]), 9)
                C.scan_finite(result, "beta2.http")
        current.save_response({"analysis_id": result["analysis_id"], "ratings": {
            "finger_control": {"qualifier": "APPROXIMATE", "value": 2.0}},
            "confidence": "MEDIUM", "notes": "beta2 fixture"})
        record = json.loads(self.responses.read_text(encoding="utf-8"))
        self.assertEqual(record["algorithm_identity"]["map_demand_version"], "0.10.0-beta.2")
        self.assertEqual(set(record["algorithm_identity"]["effective_mods"]), {"HD", "DT"})


if __name__ == "__main__":
    unittest.main()

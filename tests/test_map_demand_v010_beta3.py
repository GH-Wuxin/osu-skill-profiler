from __future__ import annotations

import copy
import unittest

from tests.test_map_demand_v010_beta2 import rows_for
from tests.test_map_demand_v01 import mini_calibration
from map_demand_v01 import model_v010_beta3 as beta
from map_demand_v01 import model_v010_beta2 as previous
from map_demand_v01 import contract as C


def measure(cs=4, dt=150, distance=120, count=100):
    return beta.precision_measure(previous._events(rows_for([dt] * count, cs=cs, distance=distance)))["value"]


class PrecisionBalanceTests(unittest.TestCase):
    def test_same_geometry_monotonic_cs_zero_to_ten(self):
        values = [measure(cs=x / 10) for x in range(101)]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))

    def test_cs8_to_10_adds_cost_instead_of_multiplying_score(self):
        a, b = measure(cs=8.1), measure(cs=10)
        self.assertLess(b, a * 1.6)
        self.assertGreater(b, a + 3)
        self.assertGreater(b, 10)  # no artificial 10 cap

    def test_large_targets_have_gentle_relief_not_an_axis_hole(self):
        for cs in (2, 3, 3.3):
            self.assertLess(measure(cs), measure(4))
            self.assertGreater(measure(cs), measure(4) * .8)

    def test_no_three_point_ceiling_at_normal_or_large_cs(self):
        self.assertGreater(measure(cs=3, dt=100), 4)
        self.assertGreater(measure(cs=4, dt=70), measure(cs=4, dt=150))

    def test_no_movement_does_not_gain_precision_from_cs_or_speed(self):
        self.assertEqual(measure(cs=10, dt=50, distance=0), 0)

    def test_distance_saturates_instead_of_becoming_jump_aim(self):
        self.assertLess(measure(distance=400), measure(distance=100) * 1.05)

    def test_easy_large_circle_slow_map_stays_low(self):
        self.assertLess(measure(cs=2, dt=1000, distance=80), 1)

    def test_cs4_branch_is_continuous(self):
        self.assertLess(abs(measure(4.00001) - measure(3.99999)), .001)

    def test_micro_evidence_survives_shrinking_targets(self):
        reports = []
        for cs in (3, 4, 8, 10):
            rows = rows_for([150] * 20, cs=cs)
            for i, row in enumerate(rows[1:]):
                row["ls.jump_distance_raw_px"] = 256 if i % 2 == 0 else 20
                row["ls.slider_aware_angle_rad"] = 0
            reports.append(beta.precision_measure(previous._events(rows)))
        self.assertGreater(reports[0]["micro_peak"], 0)
        self.assertEqual(len({r["micro_peak"] for r in reports}), 1)

    def test_empty_or_invalid_events_are_finite_zero(self):
        self.assertEqual(beta.precision_measure([])["value"], 0)
        self.assertEqual(beta.precision_measure([{"radius": 0, "dt": 100}])["value"], 0)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.rows = rows_for(([100] * 8 + [180] * 3) * 12)
        self.components, _ = beta.extract_components(self.rows)
        self.args = dict(checksum="sha256:" + "b" * 64, components=self.components,
                         calibration=mini_calibration())

    def test_other_eight_axes_exactly_unchanged(self):
        old = previous.analyze_components(**self.args)
        new = beta.analyze_components(**self.args)
        self.assertNotEqual(C.identity_cache_key(old["identity"]), C.identity_cache_key(new["identity"]))
        for axis in C.AXIS_ORDER:
            if axis != "spatial_precision":
                self.assertEqual(old["axes"][axis], new["axes"][axis], axis)

    def test_total_sr_and_mapper_bpm_cannot_set_precision(self):
        results = []
        for sr in (1, 5, 12):
            self.components["v091_nm_star_anchor"] = sr
            results.append(beta.analyze_components(**self.args)["axes"]["spatial_precision"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        a, _ = beta.extract_components(self.rows, {"bpm": 200})
        b, _ = beta.extract_components(self.rows, {"bpm": 400})
        self.assertEqual(a["beta3_precision"], b["beta3_precision"])

    def test_inputs_not_mutated(self):
        before = copy.deepcopy(self.components)
        beta.analyze_components(**self.args)
        self.assertEqual(self.components, before)

    def test_requires_own_extraction(self):
        self.components.pop("beta3_precision")
        with self.assertRaisesRegex(ValueError, "own local component extraction"):
            beta.analyze_components(**self.args)


class PublicBeta3WorkbenchTests(unittest.TestCase):
    from tests.test_bid_review_ui_v01 import BidReviewWorkbenchTests as _fixtures
    setUp = _fixtures.setUp
    tearDown = _fixtures.tearDown

    def test_runtime_and_http_preserve_other_eight_axes_and_mod_identity(self):
        from map_demand_v01 import release
        from map_demand_v01.bid_review_ui_v01 import BidReviewWorkbench
        self.assertIs(release.runtime_model("v010-beta3"), beta)
        self.assertIs(release.runtime_model("v010-beta2"), previous)
        args = dict(manifest_path=self.manifest, songs_root=self.songs,
                    calibration_path=self.calibration, responses_path=self.responses,
                    reviewer_id="tester", cache_root=self.cache)
        old = BidReviewWorkbench(**args, algorithm="v010-beta2")
        new = BidReviewWorkbench(**args, algorithm="v010-beta3")
        for mods in ([], ["HD"], ["HR"], ["DT"], ["HD", "DT"], ["EZ"], ["HT"]):
            before, after = old.analyze_bid(123456, requested_mods=mods), new.analyze_bid(123456, requested_mods=mods)
            self.assertEqual(after["status"], "OK")
            self.assertEqual(after["identity"]["map_demand_version"], beta.MAP_DEMAND_VERSION)
            self.assertNotEqual(after["analysis_id"], before["analysis_id"])
            self.assertEqual(after["identity"]["calibration_id"], new.state()["calibration_id"])
            for axis in C.AXIS_ORDER:
                if axis != "spatial_precision":
                    self.assertEqual(before["axes"][axis], after["axes"][axis], axis)


if __name__ == "__main__":
    unittest.main()

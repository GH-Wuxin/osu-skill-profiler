from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tests.test_map_demand_v01 import mini_calibration
from tests.local_pattern_fixtures import rows_for, folded
from map_demand_v01 import model_v010_beta3 as previous
from map_demand_v01 import model_v010_beta4 as beta
from map_demand_v01 import control_execution_v03 as control
from map_demand_v01 import local_pattern_geometry as geometry
from map_demand_v01 import contract as C


class PublicControlTests(unittest.TestCase):
    def setUp(self):
        self.rows = rows_for(folded())
        self.components, _ = beta.extract_components(self.rows)
        self.kwargs = dict(checksum="sha256:" + "b" * 64, components=self.components,
                           calibration=mini_calibration())

    def test_other_eight_live_axes_exactly_unchanged(self):
        old, new = previous.analyze_components(**self.kwargs), beta.analyze_components(**self.kwargs)
        self.assertEqual(new["status"], "OK")
        self.assertNotEqual(C.identity_cache_key(old["identity"]), C.identity_cache_key(new["identity"]))
        self.assertEqual(new["identity"]["map_demand_version"], "0.10.0-beta.4")
        for axis in C.AXIS_ORDER:
            if axis != "aim_control":
                self.assertEqual(old["axes"][axis], new["axes"][axis], axis)

    def test_control_exactly_equals_reviewed_v03(self):
        objects = geometry.objects(self.rows)
        expected = control.control_measure(objects, geometry.predictability(objects))
        new = beta.analyze_components(**self.kwargs)
        self.assertEqual(new["axes"]["aim_control"]["demand_star_equivalent"], expected["value"])
        self.assertEqual(self.components["beta4_control"], expected)

    def test_no_experimental_reading_extraction_or_analysis(self):
        with patch.object(control, "control_measure", wraps=control.control_measure) as calculate:
            components, _ = beta.extract_components(self.rows)
            result = beta.analyze_components(**{**self.kwargs, "components": components})
        calculate.assert_called_once()
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("reading_control_experiment", components)
        self.assertNotIn("control_relief_v02", components)

    def test_total_sr_and_old_axis_cannot_change_new_control(self):
        results = []
        for sr in (1, 7, 15):
            self.components["v091_nm_star_anchor"] = sr
            self.components["v095_control_index"] = sr
            results.append(beta.analyze_components(**self.kwargs)["axes"]["aim_control"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_source_components_not_mutated(self):
        saved = copy.deepcopy(self.components)
        beta.analyze_components(**self.kwargs)
        self.assertEqual(self.components, saved)

    def test_requires_own_extraction(self):
        self.components.pop("beta4_control")
        with self.assertRaisesRegex(ValueError, "own local component extraction"):
            beta.analyze_components(**self.kwargs)


class PublicBeta4WorkbenchTests(unittest.TestCase):
    from tests.test_bid_review_ui_v01 import BidReviewWorkbenchTests as _fixtures
    setUp = _fixtures.setUp
    tearDown = _fixtures.tearDown

    def test_workbench_mods_feedback_identity_and_rollback(self):
        from map_demand_v01 import release
        from map_demand_v01.bid_review_ui_v01 import BidReviewWorkbench
        self.assertIs(release.runtime_model("v010-beta4"), beta)
        self.assertIs(release.runtime_model("v010-beta3"), previous)
        args = dict(manifest_path=self.manifest, songs_root=self.songs, calibration_path=self.calibration,
                    responses_path=self.responses, reviewer_id="tester", cache_root=self.cache)
        old = BidReviewWorkbench(**args, algorithm="v010-beta3")
        new = BidReviewWorkbench(**args, algorithm="v010-beta4")
        for mods in ([], ["HD"], ["HR"], ["DT"], ["HD", "DT"], ["EZ"], ["HT"]):
            before, after = old.analyze_bid(123456, requested_mods=mods), new.analyze_bid(123456, requested_mods=mods)
            self.assertEqual(after["status"], "OK")
            self.assertEqual(after["identity"]["map_demand_version"], beta.MAP_DEMAND_VERSION)
            self.assertEqual(after["identity"]["calibration_id"], new.state()["calibration_id"])
            self.assertNotEqual(before["analysis_id"], after["analysis_id"])
            for axis in C.AXIS_ORDER:
                if axis != "aim_control":
                    self.assertEqual(before["axes"][axis], after["axes"][axis], (mods, axis))


if __name__ == "__main__":
    unittest.main()

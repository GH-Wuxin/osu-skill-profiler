from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_bid_review_ui_v01 as fixtures
from tests.test_map_demand_v01 import mini_calibration
from tests.test_map_demand_v07 import v07_components
from map_demand_v01 import contract as C
from map_demand_v01 import model_decoupled_v01 as experiment
from map_demand_v01 import model_v010_beta1 as beta
from map_demand_v01 import release


class PublicBetaTests(unittest.TestCase):
    def test_release_preserves_reviewed_numerical_output_and_separates_identity(self):
        for anchor in (1.2, 5.0, 8.0, 12.0):
            with self.subTest(anchor=anchor):
                components = v07_components()
                components["v091_nm_star_anchor"] = anchor
                args = dict(checksum="sha256:" + "b" * 64, components=components, calibration=mini_calibration())
                before = experiment.analyze_components(**args)
                after = beta.analyze_components(**args)
                for field in ("axes", "summaries", "archetype", "status"):
                    self.assertEqual(before[field], after[field])
                self.assertNotEqual(C.identity_cache_key(before["identity"]), C.identity_cache_key(after["identity"]))
                self.assertEqual(after["identity"]["map_demand_version"], "0.10.0-beta.1")
                self.assertEqual(after["release"]["stage"], "PUBLIC_BETA")
                self.assertEqual(after["identity"]["calibration_id"], beta.calibration_id(mini_calibration()["calibration_id"]))

    def test_selection_default_and_persistent_rollback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"SKILL_PROFILER_ALGORITHM": ""}):
            selected = Path(tmp) / "release.json"
            with patch.object(release, "RUNTIME_SELECTION_PATH", selected):
                self.assertEqual(release.default_algorithm(), "v100")
                selected.write_text('{"algorithm":"v096"}', encoding="utf-8")
                self.assertEqual(release.runtime_model().MAP_DEMAND_VERSION, "0.9.6")
                self.assertEqual(release.runtime_model("v010-beta1").MAP_DEMAND_VERSION, "0.10.0-beta.1")
                with patch.dict(os.environ, {"SKILL_PROFILER_ALGORITHM": "v010-beta1"}):
                    self.assertEqual(release.default_algorithm(), "v010-beta1")

    def test_unknown_runtime_selection_is_rejected(self):
        with patch.dict(os.environ, {"SKILL_PROFILER_ALGORITHM": "v097"}):
            with self.assertRaises(ValueError):
                release.default_algorithm()


class PublicBetaWorkbenchTests(unittest.TestCase):
    setUp = fixtures.BidReviewWorkbenchTests.setUp
    tearDown = fixtures.BidReviewWorkbenchTests.tearDown

    def test_http_contract_feedback_and_rollback_identity(self):
        args = dict(manifest_path=self.manifest, songs_root=self.songs, calibration_path=self.calibration,
                    responses_path=self.responses, reviewer_id="tester", cache_root=self.cache)
        workbench = fixtures.BidReviewWorkbench(**args, algorithm="v010-beta1")
        old = fixtures.BidReviewWorkbench(**args, algorithm="v096")
        result = workbench.analyze_bid(123456)
        self.assertEqual(workbench.state()["map_demand_version"], "0.10.0-beta.1")
        self.assertEqual(result["release"]["stage"], "PUBLIC_BETA")
        self.assertEqual(result["identity"]["calibration_id"], workbench.state()["calibration_id"])
        self.assertNotEqual(result["analysis_id"], old.analyze_bid(123456)["analysis_id"])
        workbench.save_response({"analysis_id": result["analysis_id"], "ratings": {
            "reading": {"qualifier": "APPROXIMATE", "value": 3.0}}, "confidence": "MEDIUM", "notes": "beta fixture"})
        record = json.loads(self.responses.read_text(encoding="utf-8"))
        self.assertEqual(record["algorithm_identity"]["map_demand_version"], "0.10.0-beta.1")
        self.assertEqual(record["beatmap"]["beatmap_id"], 123456)
        self.assertEqual(old.state()["map_demand_version"], "0.9.6")

from __future__ import annotations

import copy
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from map_demand_v01 import cli, release, model_v100 as stable
from map_demand_v01 import model_v010_beta92 as beta92
from tests.test_map_demand_v01 import mini_calibration
from tests.test_map_demand_v010_beta7 import synthetic_map_text
from tests.test_map_demand_v010_beta8 import analyze, TARGET_2719427
from tests.test_map_demand_v010_beta92 import (
    canonical_sha256, BETA92_CANONICAL_SHA256,
)


class Stable100Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stable100-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.osu"
        self.path.write_text(synthetic_map_text(), encoding="utf-8")

    def assert_identity_only(self, path, mods=()):
        before, old_components, old_warnings = analyze(beta92, path, mods)
        after, new_components, new_warnings = analyze(stable, path, mods)
        self.assertEqual(old_components, new_components)
        self.assertEqual(old_warnings, new_warnings)
        self.assertEqual(after["axes"], before["axes"])
        self.assertEqual(after["summaries"], before["summaries"])
        self.assertEqual(after["archetype"], before["archetype"])
        self.assertEqual(after["identity"]["map_demand_version"], "1.0.0")
        self.assertEqual(after["identity"]["algorithm_id"], "MAP_DEMAND_V100")
        self.assertEqual(after["release"]["stage"], "STABLE")
        self.assertEqual(after["release"]["basis"], "0.10.0-beta.9.2")
        self.assertEqual(
            after["diagnostics"]["release_basis_identity"], before["identity"]
        )
        # Restore only the explicitly promoted identity envelope. Everything
        # else, including warnings and nested evidence, must compare exactly.
        restored = copy.deepcopy(after)
        for key in ("identity", "schema_version", "release"):
            restored[key] = before[key]
        restored["diagnostics"]["release_basis_identity"] = (
            before["diagnostics"]["release_basis_identity"]
        )
        self.assertEqual(restored, before)
        return before

    def test_frozen_beta92_identity_only_across_mods(self):
        for mods in ((), ("HD",), ("HR",), ("HD", "HR"), ("EZ",), ("DT",), ("HT",)):
            with self.subTest(mods=mods):
                before = self.assert_identity_only(self.path, mods)
                if not mods:
                    self.assertEqual(canonical_sha256(before), BETA92_CANONICAL_SHA256)

    @unittest.skipUnless(TARGET_2719427.is_file(), "local target unavailable")
    def test_target_hdhr_keeps_all_nine_axis_payloads(self):
        self.assert_identity_only(TARGET_2719427, ("HD", "HR"))

    def test_runtime_default_and_rollback(self):
        self.assertEqual(stable.CHANGED_FROM_PREVIOUS, frozenset())
        self.assertIs(stable.extract_components, beta92.extract_components)
        self.assertIs(stable.extract_from_path, beta92.extract_from_path)
        selector = Path(self.temp.name) / "selector.json"
        with mock.patch.object(release, "RUNTIME_SELECTION_PATH", selector), mock.patch.dict(
            os.environ, {"SKILL_PROFILER_ALGORITHM": ""}
        ):
            self.assertEqual(release.default_algorithm(), "v100")
            self.assertIs(release.runtime_model(), stable)
            selector.write_text('{"algorithm":"v010-beta9.2"}', encoding="utf-8")
            self.assertIs(release.runtime_model(), beta92)

    def test_cli_and_restart_identity(self):
        calibration_dir = Path(self.temp.name) / "calibration"
        calibration_dir.mkdir()
        calibration = mini_calibration()
        calibration["distributions"]["reading_preempt_median_ms"] = [0.0, 1.0, 1000.0]
        (calibration_dir / "calibration.json").write_text(
            json.dumps(calibration), encoding="utf-8"
        )
        output = io.StringIO()
        with redirect_stdout(output):
            result = cli.main([
                "analyze", "--map", str(self.path), "--calibration-dir",
                str(calibration_dir), "--algorithm", "v100",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["release"]["version"], "1.0.0")
        script = (ROOT / "tools/restart-skill-profiler.ps1").read_text(encoding="utf-8")
        self.assertIn("'v100' = '1.0.0'", script)
        self.assertIn(f"'v100' = '{stable.ALGORITHM_ID}'", script)
        # Selection precedence is exercised by test_restart_skill_profiler.py.


if __name__ == "__main__":
    unittest.main()

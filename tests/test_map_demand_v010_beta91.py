from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v010_beta8 as beta8  # noqa: E402
from map_demand_v01 import model_v010_beta9 as beta9  # noqa: E402
from map_demand_v01 import model_v010_beta91 as beta91  # noqa: E402
from map_demand_v01 import cli, release  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v010_beta7 import synthetic_map_text  # noqa: E402
from tests.test_map_demand_v010_beta8 import analyze  # noqa: E402


BETA8_9A1D104_CANONICAL_SHA256 = (
    "3ac89bb4edb1ea096f808eae0425ca85a8c6c7403db752adae8ad065226924b6"
)
BETA9_5DCAF40_CANONICAL_SHA256 = (
    "bcce2f7320e6aa345f043524de1eefed715e7d3c4294c1254c4723e947d9675c"
)


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Beta91IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="beta91-integration-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.osu"
        self.path.write_text(synthetic_map_text(), encoding="utf-8")

    def test_beta8_and_beta9_canonical_outputs_remain_replayable(self):
        old_beta8, _components8, _warnings8 = analyze(beta8, self.path)
        old_beta9, _components9, _warnings9 = analyze(beta9, self.path)

        self.assertEqual(
            canonical_sha256(old_beta8),
            BETA8_9A1D104_CANONICAL_SHA256,
        )
        self.assertEqual(
            canonical_sha256(old_beta9),
            BETA9_5DCAF40_CANONICAL_SHA256,
        )

    def test_beta91_is_explicit_and_does_not_change_default(self):
        output, components, _warnings = analyze(beta91, self.path)

        self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
        self.assertIs(release.runtime_model("v010-beta9.1"), beta91)
        self.assertEqual(
            output["identity"]["map_demand_version"],
            "0.10.0-beta.9.1",
        )
        self.assertEqual(output["identity"]["algorithm_id"], beta91.ALGORITHM_ID)
        self.assertIn("partial_support_power_1_5_scan_v02", output["identity"]["calibration_id"])
        self.assertIn("beta91_tapping_axes", components)
        restart = (ROOT / "tools" / "restart-skill-profiler.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'v010-beta9.1'", restart)
        self.assertIn("'v010-beta9.1' = '0.10.0-beta.9.1'", restart)
        self.assertIn(f"'v010-beta9.1' = '{beta91.ALGORITHM_ID}'", restart)
        # Selection precedence is exercised by test_restart_skill_profiler.py.
        json.dumps(output, allow_nan=False)

    def test_only_raw_axis_changes_from_beta9(self):
        before, _old_components, _warnings9 = analyze(beta9, self.path)
        after, _new_components, _warnings91 = analyze(beta91, self.path)

        self.assertEqual(beta91.CHANGED_FROM_PREVIOUS, frozenset({"raw_speed"}))
        for axis in beta91.AXIS_ORDER:
            if axis in beta91.CHANGED_FROM_PREVIOUS:
                continue
            with self.subTest(axis=axis):
                self.assertEqual(after["axes"][axis], before["axes"][axis])
        self.assertEqual(
            after["axes"]["raw_speed"]["signals"]["frontier_engine"],
            "axis_support_frontier_v02",
        )

    def test_workbench_cli_selects_beta91_explicitly(self):
        calibration_dir = Path(self.temp.name) / "calibration"
        calibration_dir.mkdir()
        calibration = mini_calibration()
        calibration["distributions"]["reading_preempt_median_ms"] = [
            0.0,
            1.0,
            1000.0,
        ]
        (calibration_dir / "calibration.json").write_text(
            json.dumps(calibration),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = cli.main(
                [
                    "analyze",
                    "--map",
                    str(self.path),
                    "--calibration-dir",
                    str(calibration_dir),
                    "--algorithm",
                    "v010-beta9.1",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["identity"]["map_demand_version"],
            "0.10.0-beta.9.1",
        )


if __name__ == "__main__":
    unittest.main()

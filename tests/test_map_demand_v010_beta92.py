from __future__ import annotations

import io
import hashlib
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

from map_demand_v01 import flow_target_size_v01 as target_size  # noqa: E402
from map_demand_v01 import model_v010_beta91 as beta91  # noqa: E402
from map_demand_v01 import model_v010_beta92 as beta92  # noqa: E402
from map_demand_v01 import cli, release  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v010_beta7 import synthetic_map_text  # noqa: E402
from tests.test_map_demand_v010_beta8 import analyze  # noqa: E402


TARGET_2719427 = Path(
    r"G:\osu! 20210821\Songs\1312124 Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka"
    r"\Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka (Lasse) [Affection].osu"
)
BETA91_CANONICAL_SHA256 = (
    "61b99162cbfb8413d2bdd5b8ae9e84190ac119b94afcceadfc61f829b7fd2e5d"
)
BETA92_CANONICAL_SHA256 = (
    "328ac82abf339562a7bbc7f455278d99a70f125eb74d9ae312555dff70d083f5"
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


class Beta92IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="beta92-integration-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.osu"
        self.path.write_text(synthetic_map_text(), encoding="utf-8")

    def test_beta91_and_beta92_outputs_are_replayable(self):
        before, _old_components, _old_warnings = analyze(beta91, self.path)
        after, _new_components, _new_warnings = analyze(beta92, self.path)
        self.assertEqual(canonical_sha256(before), BETA91_CANONICAL_SHA256)
        self.assertEqual(canonical_sha256(after), BETA92_CANONICAL_SHA256)

    def test_beta92_is_explicit_and_stable_default_remains_selected(self):
        output, components, _warnings = analyze(beta92, self.path)

        self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
        self.assertIs(release.runtime_model("v010-beta9.2"), beta92)
        self.assertEqual(
            output["identity"]["map_demand_version"],
            "0.10.0-beta.9.2",
        )
        self.assertEqual(output["identity"]["algorithm_id"], beta92.ALGORITHM_ID)
        self.assertIn("flow_target_size_cs4", output["identity"]["calibration_id"])
        self.assertIn("beta92_spatial_axes", components)
        restart = (ROOT / "tools" / "restart-skill-profiler.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'v010-beta9.2'", restart)
        self.assertIn("'v010-beta9.2' = '0.10.0-beta.9.2'", restart)
        self.assertIn("$Algorithm = 'v100'", restart)
        json.dumps(output, allow_nan=False)

    def test_only_flow_axis_changes_from_beta91(self):
        before, _old_components, _old_warnings = analyze(beta91, self.path)
        after, _new_components, _new_warnings = analyze(beta92, self.path)

        self.assertEqual(beta92.CHANGED_FROM_PREVIOUS, frozenset({"flow_aim"}))
        for axis in beta92.AXIS_ORDER:
            if axis == "flow_aim":
                continue
            with self.subTest(axis=axis):
                self.assertEqual(after["axes"][axis], before["axes"][axis])
        self.assertAlmostEqual(
            after["axes"]["flow_aim"]["stars"],
            before["axes"]["flow_aim"]["stars"],
        )
        signals = after["axes"]["flow_aim"]["signals"]
        self.assertEqual(signals["target_size_reference_cs"], 4.0)
        self.assertEqual(signals["target_size_load_exponent"], 0.70)
        self.assertFalse(signals["target_size_hard_saturation"])

    def test_hr_uses_effective_cs_and_preserves_other_axes(self):
        before, _old_components, _old_warnings = analyze(beta91, self.path, ("HR",))
        after, components, _new_warnings = analyze(beta92, self.path, ("HR",))

        self.assertAlmostEqual(components["beta92_effective_circle_size"], 5.2)
        expected = target_size.adjust_flow_value(
            before["axes"]["flow_aim"]["stars"], 5.2
        )["adjusted_value"]
        self.assertAlmostEqual(after["axes"]["flow_aim"]["stars"], expected)
        for axis in beta92.AXIS_ORDER:
            if axis != "flow_aim":
                self.assertEqual(after["axes"][axis], before["axes"][axis])

    @unittest.skipUnless(TARGET_2719427.is_file(), "local BID 2719427 is unavailable")
    def test_bid_2719427_hdhr_matches_reviewed_transform(self):
        before, _old_components, _old_warnings = analyze(
            beta91, TARGET_2719427, ("HD", "HR")
        )
        after, components, _new_warnings = analyze(
            beta92, TARGET_2719427, ("HD", "HR")
        )
        self.assertAlmostEqual(components["beta92_effective_circle_size"], 5.2)
        expected = target_size.adjust_flow_value(
            before["axes"]["flow_aim"]["stars"], 5.2
        )["adjusted_value"]
        self.assertAlmostEqual(after["axes"]["flow_aim"]["stars"], expected)
        for axis in beta92.AXIS_ORDER:
            if axis != "flow_aim":
                self.assertEqual(after["axes"][axis], before["axes"][axis])

    def test_cli_selects_beta92_explicitly(self):
        calibration_dir = Path(self.temp.name) / "calibration"
        calibration_dir.mkdir()
        calibration = mini_calibration()
        calibration["distributions"]["reading_preempt_median_ms"] = [
            0.0,
            1.0,
            1000.0,
        ]
        (calibration_dir / "calibration.json").write_text(
            json.dumps(calibration), encoding="utf-8"
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
                    "v010-beta9.2",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["identity"]["map_demand_version"],
            "0.10.0-beta.9.2",
        )


if __name__ == "__main__":
    unittest.main()

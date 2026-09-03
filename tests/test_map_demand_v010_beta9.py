from __future__ import annotations

import json
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
from map_demand_v01 import release  # noqa: E402
from tests.test_map_demand_v010_beta7 import synthetic_map_text  # noqa: E402
from tests.test_map_demand_v010_beta8 import (  # noqa: E402
    TARGET_2719427,
    analyze,
)


class Beta9IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="beta9-integration-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.osu"
        self.path.write_text(synthetic_map_text(), encoding="utf-8")

    def test_beta9_is_explicitly_selectable_and_json_finite(self):
        output, components, _warnings = analyze(beta9, self.path)

        self.assertIs(release.runtime_model("v010-beta9"), beta9)
        self.assertEqual(output["identity"]["map_demand_version"], "0.10.0-beta.9")
        self.assertEqual(
            output["identity"]["algorithm_id"],
            "MAP_DEMAND_RATE_PRECISION_AREA_V010_BETA9",
        )
        self.assertIn("beta9_spatial_axes", components)
        self.assertIn("beta9_tapping_axes", components)
        json.dumps(output, allow_nan=False)

    def test_only_raw_and_precision_change_from_beta8(self):
        before, _old_components, _ = analyze(beta8, self.path)
        after, _new_components, _ = analyze(beta9, self.path)

        for axis in beta9.AXIS_ORDER:
            if axis in {"raw_speed", "spatial_precision"}:
                continue
            self.assertEqual(after["axes"][axis], before["axes"][axis])
        self.assertEqual(
            after["axes"]["spatial_precision"]["axis_contract_version"],
            beta9.REBUILT_LOCAL_AXIS_CONTRACTS["spatial_precision"],
        )
        self.assertEqual(
            after["axes"]["raw_speed"]["signals"]["partial_support_exponent"],
            1.5,
        )

    @unittest.skipUnless(TARGET_2719427.is_file(), "target map is unavailable")
    def test_real_flow_case_keeps_flow_and_recovers_precision(self):
        before, _old_components, _ = analyze(
            beta8, TARGET_2719427, mods=("HD", "HR")
        )
        after, _new_components, _ = analyze(
            beta9, TARGET_2719427, mods=("HD", "HR")
        )

        self.assertEqual(after["axes"]["flow_aim"], before["axes"]["flow_aim"])
        self.assertGreater(
            after["axes"]["spatial_precision"]["stars"],
            before["axes"]["spatial_precision"]["stars"] + 1.0,
        )
        self.assertLess(
            after["axes"]["raw_speed"]["stars"],
            before["axes"]["raw_speed"]["stars"],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v07 as v07  # noqa: E402
from map_demand_v01 import model_v08 as v08  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v07 import v07_components  # noqa: E402


class MapDemandV08Tests(unittest.TestCase):
    def test_v07_replay_is_stable_and_v08_adds_endurance_identity(self):
        calibration = mini_calibration()
        components = v07_components()
        old_before = v07.analyze_components(
            checksum="sha256:fixture", components=copy.deepcopy(components), calibration=calibration
        )
        new = v08.analyze_components(
            checksum="sha256:fixture", components=copy.deepcopy(components), calibration=calibration
        )
        old_after = v07.analyze_components(
            checksum="sha256:fixture", components=copy.deepcopy(components), calibration=calibration
        )
        self.assertEqual(old_before, old_after)
        self.assertEqual(set(old_before["axes"]), set(v07.C.AXIS_ORDER))
        self.assertEqual(set(new["axes"]), set(v08.AXIS_ORDER))
        self.assertEqual(new["identity"]["map_demand_version"], "0.8.0")
        self.assertEqual(new["schema_version"], "map_demand_v0.8.0")
        self.assertNotEqual(old_before["identity"], new["identity"])

    def test_stamina_saturates_in_time_and_is_bounded(self):
        calibration = mini_calibration()
        medium = v07_components()
        extreme = v07_components()
        medium.update(
            v07_burst_longest_duration_ms_125ms=20000.0,
            v07_burst_longest_duration_ms_250ms=20000.0,
        )
        extreme.update(
            v07_burst_longest_duration_ms_125ms=600000.0,
            v07_burst_longest_duration_ms_250ms=600000.0,
        )
        baseline = v07.analyze_components(
            checksum="sha256:baseline", components=v07_components(), calibration=calibration
        )["axes"]
        medium_axes = copy.deepcopy(baseline)
        extreme_axes = copy.deepcopy(baseline)
        v08._bounded_stamina(medium_axes, medium)
        v08._bounded_stamina(extreme_axes, extreme)
        medium_value = medium_axes["stamina"]["demand_star_equivalent"]
        extreme_value = extreme_axes["stamina"]["demand_star_equivalent"]
        self.assertAlmostEqual(medium_value, extreme_value)
        self.assertLessEqual(extreme_value, 10.0)

    def test_long_uniform_map_has_more_endurance_than_short_map(self):
        calibration = mini_calibration()
        short = v07_components()
        long = v07_components()
        short.update(
            v07_map_duration_ms=60000.0,
            v07_object_count=300.0,
            v07_density_objects_per_s=5.0,
            stamina_duration_share=0.05,
        )
        long.update(
            v07_map_duration_ms=480000.0,
            v07_object_count=3500.0,
            v07_density_objects_per_s=9.0,
            stamina_duration_share=0.90,
        )
        short_out = v08.analyze_components(
            checksum="sha256:short", components=short, calibration=calibration
        )
        long_out = v08.analyze_components(
            checksum="sha256:long", components=long, calibration=calibration
        )
        self.assertGreater(
            long_out["axes"]["endurance"]["demand_star_equivalent"],
            short_out["axes"]["endurance"]["demand_star_equivalent"],
        )
        self.assertLessEqual(long_out["axes"]["endurance"]["demand_star_equivalent"], 10.0)

    def test_nine_axis_archetype_can_report_endurance(self):
        calibration = mini_calibration()
        components = v07_components()
        components.update(
            v07_map_duration_ms=600000.0,
            v07_object_count=4000.0,
            v07_density_objects_per_s=10.0,
            stamina_duration_share=1.0,
        )
        output = v08.analyze_components(
            checksum="sha256:endurance", components=components, calibration=calibration
        )
        self.assertIn("endurance", output["archetype"]["axis_scores"])
        self.assertEqual(output["archetype"]["schema_version"], "map_archetype_v0.5.0")


if __name__ == "__main__":
    unittest.main()

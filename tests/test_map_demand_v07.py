from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model as v06  # noqa: E402
from map_demand_v01 import model_v07 as v07  # noqa: E402
from tests.test_map_demand_v01 import full_components, mini_calibration  # noqa: E402


def v07_components() -> dict:
    values = full_components()
    values.update(
        reading_hidden_pressure=0.7,
        v07_object_count=1000.0,
        v07_map_duration_ms=120000.0,
        v07_density_objects_per_s=8.0,
        v07_object_rate_max_1s=12.0,
        v07_slider_ratio=0.1,
        v07_burst_longest_duration_ms_125ms=12000.0,
        v07_burst_longest_duration_ms_250ms=16000.0,
    )
    return values


class MapDemandV07Tests(unittest.TestCase):
    def test_v06_is_replayable_and_v07_has_distinct_identity(self):
        calibration = mini_calibration()
        components = v07_components()
        old_before = v06.analyze_components(
            checksum="sha256:fixture",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        new = v07.analyze_components(
            checksum="sha256:fixture",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        old_after = v06.analyze_components(
            checksum="sha256:fixture",
            components=copy.deepcopy(components),
            calibration=calibration,
        )
        self.assertEqual(old_before, old_after)
        self.assertEqual(old_before["identity"]["map_demand_version"], "0.6.0")
        self.assertEqual(new["identity"]["map_demand_version"], "0.7.0")
        self.assertNotEqual(old_before["identity"], new["identity"])
        self.assertEqual(
            new["diagnostics"]["base_calibration_id"], calibration["calibration_id"]
        )

    def test_low_ar_is_relative_to_physical_environment(self):
        calibration = mini_calibration()
        lower = v07_components()
        harder = v07_components()
        lower["reading_preempt_median_ms"] = 650.0
        harder["reading_preempt_median_ms"] = 650.0
        # Raise objective physical components without touching AR/Reading.
        for key in (
            "jump_aim_strain_p90",
            "spatial_precision_pressure_p90",
            "raw_speed_strain_p90",
            "stamina_sustained_ms",
            "stamina_density",
        ):
            harder[key] = 1000.0
        low_out = v07.analyze_components(
            checksum="sha256:low", components=lower, calibration=calibration
        )
        high_out = v07.analyze_components(
            checksum="sha256:high", components=harder, calibration=calibration
        )
        low_diag = low_out["diagnostics"]["v07_visibility"]
        high_diag = high_out["diagnostics"]["v07_visibility"]
        self.assertLessEqual(
            high_diag["required_preempt_ms"], low_diag["required_preempt_ms"]
        )
        self.assertGreaterEqual(
            high_diag["relative_ar_deficit"], low_diag["relative_ar_deficit"]
        )

    def test_hd_compounds_existing_visibility_deficit(self):
        calibration = mini_calibration()
        components = v07_components()
        components["reading_preempt_median_ms"] = 1000.0
        transform = {
            "schema_version": "mod_transform_v0.1.0",
            "effective_mods": ["HD"],
            "clock_rate": 1.0,
            "difficulty_multiplier": {},
        }
        # Use the real transform helper's expected shape through a path-neutral
        # NM comparison and assert the mechanism itself reports a compound.
        nm = v07.analyze_components(
            checksum="sha256:nm", components=components, calibration=calibration
        )
        self.assertGreater(nm["diagnostics"]["v07_visibility"]["relative_ar_deficit"], 0)
        # Directly exercise the pure mechanism because transform readiness is
        # separately covered by the V0.6 mod-contract tests.
        axes = copy.deepcopy(nm["axes"])
        visibility = v07._visibility_mechanism(
            axes, components, calibration, {"HD"}
        )
        self.assertGreater(visibility["hidden_bonus"], 0)

    def test_sustained_regular_clicking_can_raise_finger_control(self):
        calibration = mini_calibration()
        short = v07_components()
        long = v07_components()
        short["v07_burst_longest_duration_ms_125ms"] = 500.0
        short["v07_burst_longest_duration_ms_250ms"] = 1000.0
        long["v07_burst_longest_duration_ms_125ms"] = 30000.0
        long["v07_burst_longest_duration_ms_250ms"] = 30000.0
        short_out = v07.analyze_components(
            checksum="sha256:short", components=short, calibration=calibration
        )
        long_out = v07.analyze_components(
            checksum="sha256:long", components=long, calibration=calibration
        )
        self.assertGreater(
            long_out["axes"]["finger_control"]["demand_star_equivalent"],
            short_out["axes"]["finger_control"]["demand_star_equivalent"],
        )


if __name__ == "__main__":
    unittest.main()

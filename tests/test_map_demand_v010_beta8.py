from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v010_beta7 as beta7  # noqa: E402
from map_demand_v01 import model_v010_beta8 as beta8  # noqa: E402
from map_demand_v01 import profile_semantics_v02 as semantics  # noqa: E402
from map_demand_v01 import cli, release  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v010_beta7 import synthetic_map_text  # noqa: E402


TARGET_2719427 = Path(
    r"G:\osu! 20210821\Songs\1312124 Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka"
    r"\Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka (Lasse) [Affection].osu"
)
QIAO_5216115 = ROOT / "training/datasets/map_demand_bid_cache/5216115.osu"
MREKK_5544732 = ROOT / "training/datasets/map_demand_bid_cache/5544732.osu"
CLEAR_2850471 = Path(
    r"G:\osu! 20210821\Songs\1372477 Ogura Yui - Clear Morning"
    r"\Ogura Yui - Clear Morning (-Atri-) [Hitsounds].osu"
)
MARISA_1517355 = Path(
    r"G:\osu! 20210821\Songs\710630 IOSYS - Marisa wa Taihen na Mono wo Nusunde Ikimashita"
    r"\IOSYS - Marisa wa Taihen na Mono wo Nusunde Ikimashita (DJPop) [YOLO].osu"
)
CALLING_OUT_MAYDAY_1605148 = Path(
    r"G:\osu! 20210821\Songs\756794 TheFatRat - Mayday (feat Laura Brehm)"
    r"\TheFatRat - Mayday (feat. Laura Brehm) (Voltaeyx) [[2B] Calling Out Mayday].osu"
)
BLACK_LOTUS_2841139 = Path(
    r"G:\osu! 20210821\Songs\1360992 wa - Black Lotus"
    r"\wa. - Black Lotus (blixys) [Lucilividly].osu"
)
AMEER_HS_3618238 = Path(
    r"G:\osu! 20210821\Songs\1735694 Ameer Vann - Keep Your Distance"
    r"\Ameer Vann - Keep Your Distance (mynt) [hs].osu"
)


def checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def extract(model, path: Path, mods=()):
    mods = tuple(mods)
    rows, features, metadata = model.extract_from_path(str(path), mods)
    components, warnings = model.extract_components(
        rows,
        features,
        metadata["difficulty"],
        clock_rate=metadata["mod_transform_context"].get("clock_rate", 1.0),
        effective_mods=metadata["mod_context"].get("effective_mods", ()),
        source_local_signal_version=metadata["local_signal_version"],
    )
    return rows, metadata, components, warnings


def analyze(model, path: Path, mods=()):
    _rows, metadata, components, warnings = extract(model, path, mods)
    output = model.analyze_components(
        checksum=checksum(path),
        requested_mods=tuple(mods),
        components=components,
        calibration=mini_calibration(),
        applied_mod_context=metadata["mod_transform_context"],
    )
    return output, components, warnings


class Beta8IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="beta8-integration-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.osu"
        self.path.write_text(synthetic_map_text(), encoding="utf-8")

    def test_support_aware_axes_publish_selected_frontier_and_separate_peak(self):
        output, components, _warnings = analyze(beta8, self.path)
        self.assertEqual(output["identity"]["map_demand_version"], "0.10.0-beta.8")
        self.assertIn("support_frontier_1", output["identity"]["calibration_id"])
        for axis in beta8.SUPPORT_AWARE_AXES:
            with self.subTest(axis=axis):
                item = output["axes"][axis]
                self.assertEqual(item["status"], semantics.AXIS_EMITTED)
                self.assertEqual(
                    item["axis_contract_version"],
                    semantics.AXIS_CONTRACT_VERSION,
                )
                self.assertEqual(item["stars"], item["demand_star_equivalent"])
                self.assertEqual(
                    item["stars"], item["public_frontier"]["frontier_star"]
                )
                self.assertEqual(item["score"], item["stars"] / 10.0)
                self.assertIn("star", item["physical_peak"])
                self.assertIn("value", item["evidence_confidence"])
                self.assertFalse(
                    item["public_frontier"]["confidence_affects_selection"]
                )
                self.assertFalse(
                    components[
                        "beta8_spatial_axes"
                        if axis == "jump_aim"
                        else "beta8_tapping_axes"
                    ][axis]["total_sr_used"]
                )

    def test_remaining_values_are_inherited_without_fake_frontiers(self):
        before, _old_components, _ = analyze(beta7, self.path)
        after, _new_components, _ = analyze(beta8, self.path)
        for axis, contract in beta8.INHERITED_AXIS_CONTRACTS.items():
            with self.subTest(axis=axis):
                old = before["axes"][axis]
                new = after["axes"][axis]
                self.assertEqual(
                    new["demand_star_equivalent"],
                    old["demand_star_equivalent"],
                )
                self.assertEqual(new["score"], old["score"])
                self.assertEqual(new["axis_contract_version"], contract)
                self.assertFalse(new["support_frontiers_available"])
                self.assertNotIn("physical_peak", new)

    def test_rebuilt_local_axes_publish_their_explicit_contracts(self):
        output, _components, _warnings = analyze(beta8, self.path)
        for axis, contract in beta8.REBUILT_LOCAL_AXIS_CONTRACTS.items():
            with self.subTest(axis=axis):
                item = output["axes"][axis]
                self.assertEqual(item["axis_contract_version"], contract)
                self.assertEqual(item["stars"], item["demand_star_equivalent"])
                self.assertEqual(
                    item["public_value_semantics"],
                    "BETA8_LOCAL_MECHANISM_AXIS_VALUE",
                )
                self.assertFalse(item["support_frontiers_available"])

    def test_confidence_mutation_cannot_change_support_values(self):
        _rows, metadata, components, _warnings = extract(beta8, self.path)
        changed = copy.deepcopy(components)
        for key, axis in (
            ("beta8_spatial_axes", "jump_aim"),
            ("beta8_tapping_axes", "raw_speed"),
        ):
            changed[key][axis]["evidence_confidence"] = 0.01
            details = changed[key][axis].get("evidence_confidence_details")
            if isinstance(details, dict):
                details["value"] = 0.01
        kwargs = {
            "checksum": checksum(self.path),
            "calibration": mini_calibration(),
            "requested_mods": (),
            "applied_mod_context": metadata["mod_transform_context"],
        }
        baseline = beta8.analyze_components(components=components, **kwargs)
        mutated = beta8.analyze_components(components=changed, **kwargs)
        for axis in beta8.SUPPORT_AWARE_AXES:
            self.assertEqual(
                baseline["axes"][axis]["stars"],
                mutated["axes"][axis]["stars"],
            )
            self.assertEqual(
                baseline["axes"][axis]["physical_peak"],
                mutated["axes"][axis]["physical_peak"],
            )

    def test_output_is_finite_json_and_beta7_replays_identically(self):
        _rows, metadata, old_components, _warnings = extract(beta7, self.path)
        kwargs = {
            "checksum": checksum(self.path),
            "components": old_components,
            "calibration": mini_calibration(),
            "requested_mods": (),
            "applied_mod_context": metadata["mod_transform_context"],
        }
        before = beta7.analyze_components(**kwargs)
        beta8_output, _new_components, _ = analyze(beta8, self.path)
        replay = beta7.analyze_components(**kwargs)
        self.assertEqual(before, replay)
        json.dumps(beta8_output, allow_nan=False)

    def test_beta8_is_explicitly_selectable_without_changing_default(self):
        self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
        self.assertIs(release.runtime_model("v010-beta8"), beta8)
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
                    "v010-beta8",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["identity"]["map_demand_version"], "0.10.0-beta.8"
        )
        restart = (ROOT / "tools" / "restart-skill-profiler.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'v010-beta8'", restart)
        self.assertIn("'v010-beta8' = '0.10.0-beta.8'", restart)
        self.assertIn("$Algorithm = 'v100'", restart)


@unittest.skipUnless(TARGET_2719427.is_file(), "target map is unavailable")
class Beta8TargetTests(unittest.TestCase):
    def test_2719427_hdhr_is_flow_led_while_short_raw_peak_stays_visible(self):
        output, _components, _warnings = analyze(
            beta8, TARGET_2719427, mods=("HD", "HR")
        )
        axes = output["axes"]
        flow = axes["flow_aim"]["demand_star_equivalent"]
        self.assertGreater(flow, axes["jump_aim"]["stars"])
        self.assertGreater(flow, axes["raw_speed"]["stars"])
        self.assertGreater(
            axes["raw_speed"]["physical_peak"]["star"],
            axes["raw_speed"]["stars"],
        )
        self.assertEqual(
            axes["jump_aim"]["public_frontier"]["selected_component"],
            "recurrence",
        )
        self.assertNotIn(
            "recurrence",
            axes["raw_speed"]["public_frontier"]["eligible_components"],
        )
        self.assertGreaterEqual(
            axes["raw_speed"]["establishment"]["winning_episode_sample_count"],
            16,
        )
        self.assertLess(
            axes["raw_speed"]["establishment"]["winning_threshold_star"],
            axes["raw_speed"]["physical_peak"]["star"],
        )

    @unittest.skipUnless(QIAO_5216115.is_file(), "qiao map is unavailable")
    @unittest.skipUnless(MREKK_5544732.is_file(), "mrekk map is unavailable")
    def test_simple_jump_midscale_falls_while_real_extreme_tail_remains(self):
        qiao, _qiao_components, _ = analyze(beta8, QIAO_5216115)
        mrekk, _mrekk_components, _ = analyze(
            beta8, MREKK_5544732, mods=("HD", "HR", "DT")
        )
        qiao_jump = qiao["axes"]["jump_aim"]
        mrekk_jump = mrekk["axes"]["jump_aim"]
        self.assertLess(qiao_jump["stars"], 7.0)
        self.assertGreater(mrekk_jump["stars"], 12.0)
        self.assertGreater(
            mrekk_jump["physical_peak"]["star"], 12.0
        )
        self.assertGreater(
            mrekk_jump["stars"] - qiao_jump["stars"], 5.0
        )
        self.assertGreater(
            mrekk_jump["physical_peak"]["star"]
            - qiao_jump["physical_peak"]["star"],
            4.0,
        )

    @unittest.skipUnless(CLEAR_2850471.is_file(), "Clear Morning unavailable")
    @unittest.skipUnless(MARISA_1517355.is_file(), "Marisa unavailable")
    def test_short_burst_peak_and_sustained_speed_are_not_conflated(self):
        clear, _clear_components, _ = analyze(beta8, CLEAR_2850471)
        marisa, _marisa_components, _ = analyze(beta8, MARISA_1517355)
        clear_raw = clear["axes"]["raw_speed"]
        marisa_raw = marisa["axes"]["raw_speed"]
        self.assertGreater(
            clear_raw["physical_peak"]["star"],
            marisa_raw["physical_peak"]["star"],
        )
        self.assertGreater(marisa_raw["stars"], clear_raw["stars"])
        self.assertGreater(
            marisa_raw["sustain"]["frontier_star"],
            clear_raw["sustain"]["frontier_star"],
        )
        self.assertEqual(
            clear["diagnostics"]["beta8_input_role"]["role"],
            beta8.AUXILIARY_HITSOUND_INPUT_ROLE,
        )
        self.assertIn(
            "BETA8_AUXILIARY_HITSOUND_LAYER",
            {warning.get("code") for warning in clear["warnings"]},
        )

    @unittest.skipUnless(
        CALLING_OUT_MAYDAY_1605148.is_file(), "2B fixture unavailable"
    )
    def test_concurrent_active_slider_map_abstains_from_single_cursor_jump(self):
        output, components, _warnings = analyze(beta8, CALLING_OUT_MAYDAY_1605148)
        jump = output["axes"]["jump_aim"]
        alternative = components["beta8_spatial_axes"]["jump_aim"]["signals"][
            "alternative_mechanism"
        ]
        self.assertEqual(jump["status"], semantics.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(jump["stars"])
        self.assertGreater(alternative["excluded_transition_count"], 0)
        self.assertGreaterEqual(alternative["max_concurrent_active_sliders"], 2)
        self.assertIn(
            "BETA8_CONCURRENT_ACTIVE_SLIDER_ALTERNATIVE_MECHANISM",
            {warning.get("code") for warning in output["warnings"]},
        )

    @unittest.skipUnless(BLACK_LOTUS_2841139.is_file(), "geometry fixture unavailable")
    def test_implausible_slider_geometry_is_excluded_without_a_star_cap(self):
        output, components, _warnings = analyze(beta8, BLACK_LOTUS_2841139)
        jump = output["axes"]["jump_aim"]
        alternative = components["beta8_spatial_axes"]["jump_aim"]["signals"][
            "alternative_mechanism"
        ]
        self.assertGreater(
            alternative["invalid_single_cursor_geometry_count"], 0
        )
        self.assertLess(jump["stars"], 20.0)
        self.assertIn(
            "BETA8_INVALID_SINGLE_CURSOR_GEOMETRY_EXCLUDED",
            {warning.get("code") for warning in output["warnings"]},
        )

    @unittest.skipUnless(AMEER_HS_3618238.is_file(), "hs fixture unavailable")
    def test_hs_abbreviation_requires_structural_auxiliary_corroboration(self):
        output, _components, _warnings = analyze(beta8, AMEER_HS_3618238)
        role = output["diagnostics"]["beta8_input_role"]

        self.assertEqual(role["role"], beta8.AUXILIARY_HITSOUND_INPUT_ROLE)
        self.assertEqual(
            role["source"],
            "HS_TOKEN_WITH_SINGLE_POSITION_ALL_CIRCLE_CORROBORATION",
        )
        self.assertEqual(role["unique_start_position_count"], 1)
        self.assertEqual(role["slider_count"], 0)


if __name__ == "__main__":
    unittest.main()

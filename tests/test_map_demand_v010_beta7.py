from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v010_beta7 as beta7  # noqa: E402
from map_demand_v01 import profile_semantics_v01 as semantics  # noqa: E402
from map_demand_v01 import release  # noqa: E402
from map_demand_v01 import cli  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402


TARGET_2719427 = Path(
    r"G:\osu! 20210821\Songs\1312124 Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka"
    r"\Ayase Rie - Hijitsuzaikei Joshitachi wa Dou Surya Ii Desu ka (Lasse) [Affection].osu"
)


def synthetic_map_text(
    *,
    object_count: int = 80,
    include_ar: bool = True,
    simultaneous_index: int | None = None,
) -> str:
    difficulty = [
        "HPDrainRate:5",
        "CircleSize:4",
        "OverallDifficulty:8",
    ]
    if include_ar:
        difficulty.append("ApproachRate:9")
    difficulty.extend(("SliderMultiplier:1.4", "SliderTickRate:1"))

    intervals = (80, 120, 160, 100, 200, 90, 150, 110)
    time_ms = 1000
    objects: list[str] = []
    previous_time = time_ms
    for index in range(object_count):
        if index:
            time_ms += intervals[(index - 1) % len(intervals)]
        if simultaneous_index is not None and index == simultaneous_index:
            time_ms = previous_time
        theta = index * 0.53
        radius = 72 + 24 * math.sin(index * 0.31)
        x = round(256 + radius * math.cos(theta))
        y = round(192 + radius * math.sin(theta))
        objects.append(f"{x},{y},{time_ms},1,0,0:0:0:0:")
        previous_time = time_ms

    return "\n".join(
        [
            "osu file format v14",
            "[General]",
            "Mode:0",
            "[Metadata]",
            "Title:beta7 integration fixture",
            "Artist:test",
            "Creator:test",
            "Version:contract",
            "[Difficulty]",
            *difficulty,
            "[TimingPoints]",
            "0,500,4,2,1,60,1,0",
            "[HitObjects]",
            *objects,
            "",
        ]
    )


def _checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def extract_beta7(path: Path, mods=()):
    mods = tuple(mods)
    rows, features, metadata = beta7.extract_from_path(str(path), mods)
    components, warnings = beta7.extract_components(
        rows,
        features,
        metadata["difficulty"],
        clock_rate=metadata["mod_transform_context"].get("clock_rate", 1.0),
        effective_mods=metadata["mod_context"].get("effective_mods", ()),
        source_local_signal_version=metadata["local_signal_version"],
    )
    return rows, features, metadata, components, warnings


def analyze_beta7(
    path: Path,
    *,
    mods=(),
    calibration=None,
    components=None,
):
    rows, features, metadata, extracted, warnings = extract_beta7(path, mods)
    active_components = extracted if components is None else components
    output = beta7.analyze_components(
        checksum=_checksum(path),
        requested_mods=tuple(mods),
        components=active_components,
        calibration=mini_calibration() if calibration is None else calibration,
        applied_mod_context=metadata["mod_transform_context"],
    )
    return output, rows, features, metadata, extracted, warnings


def axis_values(output: dict) -> dict[str, float | None]:
    return {
        axis: output["axes"][axis].get("demand_star_equivalent")
        for axis in beta7.AXIS_ORDER
    }


class Beta7IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="beta7-integration-")
        self.addCleanup(self.temp.cleanup)
        self.map_path = Path(self.temp.name) / "fixture.osu"
        self.map_path.write_text(synthetic_map_text(), encoding="utf-8")

    def test_all_nine_axes_are_replaced_by_beta7_local_evidence(self):
        output, _rows, _features, _metadata, components, _warnings = analyze_beta7(
            self.map_path
        )
        self.assertEqual(output["status"], "OK")
        self.assertEqual(output["identity"]["map_demand_version"], "0.10.0-beta.7")
        self.assertIn(":spatial_3:", output["identity"]["calibration_id"])
        self.assertIn(":tapping_3:", output["identity"]["calibration_id"])
        self.assertEqual(
            output["axes"]["flow_aim"]["method"],
            "CONTINUOUS_DIRECTIONAL_PATH_FLOW_V03",
        )
        self.assertEqual(
            output["axes"]["flow_aim"]["scale_method"],
            "LOCAL_DIRECTIONAL_PATH_PHYSICAL_LOG_NO_TOTAL_SR_V03",
        )
        self.assertEqual(
            output["axes"]["raw_speed"]["method"],
            "RUN_LOCAL_RAW_SPEED_V03",
        )
        self.assertEqual(
            output["axes"]["raw_speed"]["scale_method"],
            "INDEPENDENT_PHYSICAL_RATE_NO_TOTAL_SR_V03",
        )

        for axis in beta7.AXIS_ORDER:
            with self.subTest(axis=axis):
                item = output["axes"][axis]
                self.assertEqual(item["status"], semantics.AXIS_EMITTED)
                self.assertEqual(
                    item["evidence"][0]["component"], f"beta7_{axis}"
                )
                self.assertEqual(
                    item["evidence"][0]["evidence_tag"],
                    "PUBLIC_BETA7_INDEPENDENT_EVIDENCE",
                )
                self.assertEqual(
                    output["diagnostics"]["beta7_axis_dependencies"][axis],
                    ["BEATMAP_LOCAL_EVIDENCE_ONLY"],
                )
                self.assertNotIn("SOFT_TOTAL_SR_ANCHOR", item["scale_method"])
                self.assertEqual(
                    item["score_semantics"],
                    "VALUE_DIV_10_DISPLAY_RATIO_NOT_PROBABILITY",
                )

        for axis in semantics.AIM_STAR_AXES:
            measure = components["beta7_spatial_axes"][axis]
            with self.subTest(spatial_axis=axis):
                self.assertFalse(measure["total_sr_used"])
        for axis, measure in components["beta7_tapping_axes"].items():
            with self.subTest(tapping_axis=axis):
                self.assertFalse(measure["total_sr_used"])
        self.assertFalse(components["beta7_reading"]["total_sr_used"])
        self.assertEqual(
            output["axes"]["reading"]["method"],
            "LOCAL_ORDER_MEMORY_READING_V03",
        )
        self.assertIn("reading_3", output["identity"]["calibration_id"])
        self.assertIn(
            "profile_semantics_2",
            output["identity"]["calibration_id"],
        )
        self.assertIn(
            "component_context_1",
            output["identity"]["calibration_id"],
        )
        self.assertEqual(
            output["archetype"]["policy_id"],
            "SEVEN_STAR_AXIS_DOMINANCE_WITH_BOUNDED_AUXILIARY_V02",
        )
        self.assertEqual(
            output["diagnostics"]["beta7_total_sr_role"],
            "DIAGNOSTIC_ONLY_NOT_AN_AXIS_INPUT",
        )
        self.assertEqual(
            output["diagnostics"]["beta7_component_effective_mods"],
            [],
        )

    def test_component_mod_provenance_fails_closed_on_nm_hd_reuse(self):
        _rows, _features, _metadata, hd_components, _warnings = extract_beta7(
            self.map_path,
            mods=("HD",),
        )
        _nm_rows, _nm_features, nm_metadata, _nm_components, _nm_warnings = (
            extract_beta7(self.map_path)
        )

        with self.assertRaisesRegex(ValueError, "component mod provenance mismatch"):
            beta7.analyze_components(
                checksum=_checksum(self.map_path),
                requested_mods=(),
                components=hd_components,
                calibration=mini_calibration(),
                applied_mod_context=nm_metadata["mod_transform_context"],
            )

    def test_nc_request_matches_canonical_dt_component_context(self):
        output, _rows, _features, _metadata, components, _warnings = analyze_beta7(
            self.map_path,
            mods=("NC",),
        )
        self.assertEqual(components["beta7_effective_mods"], ["DT"])
        self.assertEqual(
            output["diagnostics"]["beta7_component_effective_mods"],
            ["DT"],
        )

    def test_total_sr_anchor_and_legacy_calibration_do_not_change_axis_values(self):
        _rows, _features, _metadata, components, _warnings = extract_beta7(
            self.map_path
        )
        low_anchor = copy.deepcopy(components)
        high_anchor = copy.deepcopy(components)
        low_anchor["v091_nm_star_anchor"] = 1.0
        high_anchor["v091_nm_star_anchor"] = 30.0

        old_calibration_a = mini_calibration(seed=11)
        old_calibration_b = mini_calibration(seed=913)
        self.assertNotEqual(
            old_calibration_a["distributions"],
            old_calibration_b["distributions"],
        )
        baseline = beta7.analyze_components(
            checksum=_checksum(self.map_path),
            components=low_anchor,
            calibration=old_calibration_a,
        )
        anchor_changed = beta7.analyze_components(
            checksum=_checksum(self.map_path),
            components=high_anchor,
            calibration=old_calibration_a,
        )
        calibration_changed = beta7.analyze_components(
            checksum=_checksum(self.map_path),
            components=low_anchor,
            calibration=old_calibration_b,
        )

        self.assertEqual(axis_values(baseline), axis_values(anchor_changed))
        self.assertEqual(axis_values(baseline), axis_values(calibration_changed))
        for axis, value in axis_values(baseline).items():
            with self.subTest(axis=axis):
                self.assertIsNotNone(value)

    def test_missing_ar_materialises_od_before_hr_and_hd_remains_analysable(self):
        path = Path(self.temp.name) / "missing-ar.osu"
        path.write_text(
            synthetic_map_text(include_ar=False),
            encoding="utf-8",
        )
        output, _rows, _features, metadata, components, _warnings = analyze_beta7(
            path,
            mods=("HD", "HR"),
        )

        self.assertNotIn("ApproachRate", metadata["source_difficulty"])
        self.assertTrue(metadata["legacy_ar_fallback_applied"])
        self.assertEqual(
            metadata["difficulty"]["ApproachRate"],
            10.0,
        )
        self.assertEqual(
            metadata["mod_transform_context"]["difficulty_changes"]
            ["ApproachRate"]["provenance"],
            "LEGACY_AR_FALLBACK_TO_OD",
        )
        self.assertIn(components["beta7_reading"]["status"], {"FULL", "DEGRADED"})
        self.assertEqual(output["status"], "OK")
        self.assertEqual(output["axes"]["reading"]["status"], semantics.AXIS_EMITTED)
        self.assertIn("HD", output["identity"]["effective_mods"])
        self.assertIn("HR", output["identity"]["effective_mods"])

    def test_simultaneous_objects_are_isolated_per_axis_without_throwing(self):
        path = Path(self.temp.name) / "simultaneous.osu"
        path.write_text(
            synthetic_map_text(object_count=20, simultaneous_index=2),
            encoding="utf-8",
        )
        output, _rows, _features, _metadata, components, _warnings = analyze_beta7(
            path
        )

        self.assertGreater(
            components["beta7_geometry_summary"]["simultaneous_group_count"],
            0,
        )
        # Reading can safely retain independent order sections because the
        # simultaneous group and both causal boundaries are absent from its
        # eligible core.  The structural ambiguity still caps quality.
        self.assertEqual(
            components["beta7_reading"]["status"],
            "DEGRADED",
        )
        self.assertEqual(
            components["beta7_reading"]["reason"],
            "ISOLATED_SIMULTANEOUS_ORDER",
        )
        self.assertEqual(
            output["axes"]["reading"]["status"],
            semantics.AXIS_EMITTED,
        )

    def test_single_object_missing_evidence_is_not_observed_zero(self):
        path = Path(self.temp.name) / "single.osu"
        path.write_text(
            synthetic_map_text(object_count=1),
            encoding="utf-8",
        )
        output, *_rest = analyze_beta7(path)

        for axis in beta7.AXIS_ORDER:
            with self.subTest(axis=axis):
                item = output["axes"][axis]
                self.assertEqual(item["status"], semantics.INSUFFICIENT_EVIDENCE)
                self.assertIsNone(item["demand_star_equivalent"])
                self.assertIsNone(item["score"])
                envelope = item["evidence"][0]["measure"]["evidence"]
                self.assertFalse(envelope["observed_zero"])
        self.assertEqual(
            output["summaries"]["primary_star_summary"]["status"],
            semantics.INSUFFICIENT_EVIDENCE,
        )

    def test_summaries_never_mix_bounded_and_star_units(self):
        output, *_rest = analyze_beta7(self.map_path)
        summaries = output["summaries"]

        self.assertEqual(
            summaries["aim_star_summary"]["source_axes"],
            list(semantics.AIM_STAR_AXES),
        )
        self.assertEqual(
            summaries["tapping_star_summary"]["source_axes"],
            ["raw_speed", "finger_control"],
        )
        self.assertEqual(
            summaries["primary_star_summary"]["source_axes"],
            list(semantics.STAR_AXES),
        )
        self.assertEqual(
            summaries["bounded_sustain_summary"]["source_axes"],
            ["stamina", "endurance"],
        )
        self.assertEqual(
            summaries["bounded_sustain_summary"]["unit"],
            "bounded_0_10",
        )
        self.assertEqual(
            summaries["overall_demand"]["status"],
            semantics.NOT_PUBLISHED_MIXED_UNITS,
        )
        self.assertIsNone(summaries["overall_demand"]["value"])
        self.assertIsNone(summaries["overall_demand"]["score"])
        self.assertEqual(
            summaries["primary_star_summary"]["interpretation"],
            semantics.STAR_SUMMARY_INTERPRETATION,
        )
        self.assertEqual(
            summaries["bounded_sustain_summary"]["interpretation"],
            semantics.BOUNDED_SUMMARY_INTERPRETATION,
        )
        for name in (
            "aim_star_summary",
            "tapping_star_summary",
            "primary_star_summary",
            "bounded_sustain_summary",
        ):
            self.assertEqual(summaries[name]["confidence"], "LOW")

    def test_beta1_through_beta6_still_import_and_replay(self):
        calibration = mini_calibration(seed=41)
        checksum = _checksum(self.map_path)
        for number in range(1, 7):
            with self.subTest(beta=number):
                module = importlib.import_module(
                    f"map_demand_v01.model_v010_beta{number}"
                )
                rows, features, metadata = module.extract_from_path(
                    str(self.map_path)
                )
                component_kwargs = {}
                if hasattr(module, "EXPECTED_LOCAL_SIGNAL_VERSION"):
                    component_kwargs["source_local_signal_version"] = metadata[
                        "local_signal_version"
                    ]
                components, _warnings = module.extract_components(
                    rows,
                    features,
                    metadata["difficulty"],
                    **component_kwargs,
                )
                components["v091_nm_star_anchor"] = 6.0
                kwargs = {
                    "checksum": checksum,
                    "components": components,
                    "calibration": calibration,
                }
                first = module.analyze_components(**kwargs)
                second = module.analyze_components(**kwargs)
                self.assertEqual(
                    first["identity"]["map_demand_version"],
                    f"0.10.0-beta.{number}",
                )
                self.assertEqual(first["status"], "OK")
                self.assertEqual(first["axes"], second["axes"])

    def test_beta7_is_selectable_with_stable_default(self):
        self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
        self.assertIs(release.runtime_model("v010-beta7"), beta7)

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
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(
                [
                    "analyze",
                    "--map",
                    str(self.map_path),
                    "--calibration-dir",
                    str(calibration_dir),
                    "--algorithm",
                    "v010-beta7",
                    "--star-anchor",
                    "300",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["identity"]["map_demand_version"],
            "0.10.0-beta.7",
        )
        self.assertEqual(
            payload["diagnostics"]["beta7_total_sr_role"],
            "DIAGNOSTIC_ONLY_NOT_AN_AXIS_INPUT",
        )

        restart = (ROOT / "tools" / "restart-skill-profiler.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'v010-beta7'", restart)
        self.assertIn("'v010-beta7' = '0.10.0-beta.7'", restart)
        self.assertIn("$Algorithm = 'v100'", restart)


@unittest.skipUnless(
    TARGET_2719427.is_file(),
    "local BID 2719427 source is unavailable",
)
class Target2719427Beta7Tests(unittest.TestCase):
    def test_hdhr_flow_exceeds_all_spatial_peers_without_hardcoded_score(self):
        output, *_rest = analyze_beta7(TARGET_2719427, mods=("HD", "HR"))
        axes = output["axes"]
        flow = axes["flow_aim"]["demand_star_equivalent"]
        self.assertEqual(axes["flow_aim"]["status"], semantics.AXIS_EMITTED)
        for peer in ("jump_aim", "aim_control", "spatial_precision"):
            with self.subTest(peer=peer):
                self.assertEqual(axes[peer]["status"], semantics.AXIS_EMITTED)
                self.assertGreater(
                    flow,
                    axes[peer]["demand_star_equivalent"],
                )
        self.assertFalse(
            output["diagnostics"]["beta7_spatial_axes"]["flow_aim"]
            ["total_sr_used"]
        )
        self.assertEqual(output["archetype"]["confidence"], "LOW")
        self.assertEqual(
            output["archetype"]["descriptor_semantics"],
            semantics.DESCRIPTOR_SEMANTICS,
        )


if __name__ == "__main__":
    unittest.main()

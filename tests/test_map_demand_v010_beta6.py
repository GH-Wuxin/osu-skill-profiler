from __future__ import annotations

import copy
import io
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01 import cli  # noqa: E402
from map_demand_v01 import model_v010_beta5 as previous  # noqa: E402
from map_demand_v01 import model_v010_beta6 as beta  # noqa: E402
from map_demand_v01 import release  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402


def map_text(*, compound: bool) -> str:
    slider = (
        "64,64,1000,2,0,B|164:64|164:64|164:164,1,200,0:0:0:0:"
        if compound
        else "64,64,1000,2,0,L|164:64|164:164,1,200,0:0:0:0:"
    )
    objects = [
        slider,
        "220,164,1200,1,0",
        "280,120,1300,1,0",
        "340,164,1400,1,0",
        "400,120,1500,1,0",
        "460,164,1600,1,0",
        "400,220,1700,1,0",
        "340,270,1800,1,0",
        "280,220,1900,1,0",
        "220,270,2000,1,0",
        "160,220,2100,1,0",
        "100,270,2200,1,0",
    ]
    return "\n".join(
        [
            "osu file format v14",
            "[General]",
            "Mode:0",
            "[Difficulty]",
            "HPDrainRate:5",
            "CircleSize:4",
            "OverallDifficulty:8",
            "ApproachRate:9",
            "SliderMultiplier:1",
            "SliderTickRate:1",
            "[TimingPoints]",
            "0,500,4,2,1,60,1,0",
            "[HitObjects]",
            *objects,
        ]
    ) + "\n"


def circle_chain_text(points: list[tuple[int, int]]) -> str:
    objects = [
        f"{x},{y},{1000 + index * 100},1,0"
        for index, (x, y) in enumerate(points)
    ]
    return "\n".join(
        [
            "osu file format v14",
            "[General]",
            "Mode:0",
            "[Difficulty]",
            "HPDrainRate:5",
            "CircleSize:4",
            "OverallDifficulty:8",
            "ApproachRate:9",
            "SliderMultiplier:1",
            "SliderTickRate:1",
            "[TimingPoints]",
            "0,500,4,2,1,60,1,0",
            "[HitObjects]",
            *objects,
        ]
    ) + "\n"


class PublicBeta6Tests(unittest.TestCase):
    def _extract(self, *, compound: bool):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "map.osu"
        path.write_text(map_text(compound=compound), encoding="utf-8")
        old_rows, old_features, old_metadata = previous.extract_from_path(str(path))
        new_rows, new_features, new_metadata = beta.extract_from_path(str(path))
        return (
            temp,
            (old_rows, old_features, old_metadata),
            (new_rows, new_features, new_metadata),
        )

    def test_beta5_replay_stays_local03_and_beta6_explicitly_uses_local04(self):
        temp, old, new = self._extract(compound=True)
        self.addCleanup(temp.cleanup)
        old_rows, _, old_metadata = old
        new_rows, _, new_metadata = new

        self.assertNotIn("local_signal_version", old_metadata)
        self.assertEqual(
            set(old_metadata),
            {
                "path",
                "object_count",
                "feature_count",
                "difficulty",
                "effective_difficulty",
                "source_difficulty",
                "mod_context",
                "mod_transform_context",
            },
        )
        self.assertEqual(new_metadata["local_signal_version"], "0.4.0")
        self.assertNotEqual(
            old_rows[0]["ls.lazy_end_position_x_px"],
            new_rows[0]["ls.lazy_end_position_x_px"],
        )

    def test_only_jump_and_flow_formulas_change_on_duplicate_free_geometry(self):
        temp, old, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        old_rows, old_features, old_metadata = old
        new_rows, new_features, new_metadata = new
        self.assertEqual(old_rows, new_rows)

        old_components, _ = previous.extract_components(
            old_rows,
            old_features,
            old_metadata["difficulty"],
        )
        new_components, _ = beta.extract_components(
            new_rows,
            new_features,
            new_metadata["difficulty"],
            source_local_signal_version=new_metadata["local_signal_version"],
        )
        old_components["v091_nm_star_anchor"] = 7.0
        new_components["v091_nm_star_anchor"] = 7.0
        checksum = "sha256:" + "6" * 64
        calibration = mini_calibration()
        old_output = previous.analyze_components(
            checksum=checksum,
            components=old_components,
            calibration=calibration,
        )
        new_output = beta.analyze_components(
            checksum=checksum,
            components=new_components,
            calibration=calibration,
        )

        self.assertEqual(new_output["identity"]["local_signal_version"], "0.4.0")
        self.assertEqual(
            new_output["diagnostics"]["release_basis_identity"][
                "local_signal_version"
            ],
            "0.4.0",
        )
        self.assertEqual(new_output["identity"]["map_demand_version"], beta.MAP_DEMAND_VERSION)
        self.assertNotEqual(
            C.identity_cache_key(old_output["identity"]),
            C.identity_cache_key(new_output["identity"]),
        )
        for axis in C.AXIS_ORDER:
            if axis not in {"jump_aim", "flow_aim"}:
                self.assertEqual(old_output["axes"][axis], new_output["axes"][axis], axis)
        for axis in ("jump_aim", "flow_aim"):
            self.assertEqual(
                new_output["axes"][axis]["method"],
                "COHERENT_SLIDER_AWARE_AIM_ROUTING_V1",
            )
            self.assertEqual(new_output["axes"][axis]["evidence"][0]["evidence_tag"], "PUBLIC_BETA6")

    def test_analysis_requires_exact_beta6_component(self):
        temp, _, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        rows, features, metadata = new
        components, _ = beta.extract_components(
            rows,
            features,
            metadata["difficulty"],
            source_local_signal_version=metadata["local_signal_version"],
        )
        components["beta6_aim_routing"]["jump"].pop("support")
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            beta.analyze_components(
                checksum="sha256:" + "6" * 64,
                components=components,
                calibration=mini_calibration(),
            )

    def test_analysis_does_not_mutate_components(self):
        temp, _, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        rows, features, metadata = new
        components, _ = beta.extract_components(
            rows,
            features,
            metadata["difficulty"],
            source_local_signal_version=metadata["local_signal_version"],
        )
        saved = copy.deepcopy(components)
        beta.analyze_components(
            checksum="sha256:" + "6" * 64,
            components=components,
            calibration=mini_calibration(),
        )
        self.assertEqual(components, saved)

    def test_beta6_refuses_unlabelled_or_local03_component_sources(self):
        temp, old, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        old_rows, old_features, old_metadata = old
        with self.assertRaisesRegex(ValueError, "require Local Signal 0.4.0"):
            beta.extract_components(
                old_rows,
                old_features,
                old_metadata["difficulty"],
                source_local_signal_version=C.LOCAL_SIGNAL_VERSION,
            )
        with self.assertRaisesRegex(ValueError, "rows returned by beta6"):
            beta.extract_components(
                old_rows,
                old_features,
                old_metadata["difficulty"],
                source_local_signal_version=beta.EXPECTED_LOCAL_SIGNAL_VERSION,
            )

        rows, features, metadata = new
        with self.assertRaises(TypeError):
            beta.extract_components(rows, features, metadata["difficulty"])
        with self.assertRaisesRegex(ValueError, "rows returned by beta6"):
            beta.extract_components(
                list(rows),
                features,
                metadata["difficulty"],
                source_local_signal_version=metadata["local_signal_version"],
            )

    def test_beta6_refuses_rows_mutated_after_trusted_extraction(self):
        temp, _, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        rows, features, metadata = new
        rows[0]["ls.start_time_ms"] += 1.0

        with self.assertRaisesRegex(ValueError, "changed after extraction"):
            beta.extract_components(
                rows,
                features,
                metadata["difficulty"],
                source_local_signal_version=metadata["local_signal_version"],
            )

    def test_analysis_refuses_tampered_component_provenance(self):
        temp, _, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        rows, features, metadata = new
        components, _ = beta.extract_components(
            rows,
            features,
            metadata["difficulty"],
            source_local_signal_version=metadata["local_signal_version"],
        )
        components["beta6_source_local_signal_version"] = "0.3.0"
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            beta.analyze_components(
                checksum="sha256:" + "6" * 64,
                components=components,
                calibration=mini_calibration(),
            )

    def test_real_extractor_chain_note_basis_and_coverage(self):
        square = [(100, 100), (200, 100), (200, 200), (100, 200), (100, 100)]
        for count in (3, 4, 5):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "chain.osu"
                path.write_text(
                    circle_chain_text(square[:count]),
                    encoding="utf-8",
                )
                rows, features, metadata = beta.extract_from_path(str(path))
                angles = [item.get("ls.slider_aware_angle_rad") for item in rows]
                self.assertEqual(angles[:2], [None, None])
                for angle in angles[2:]:
                    self.assertAlmostEqual(angle, math.pi / 2.0)

                components, _ = beta.extract_components(
                    rows,
                    features,
                    metadata["difficulty"],
                    source_local_signal_version=metadata["local_signal_version"],
                )
                flow = components["beta6_aim_routing"]["flow"]
                self.assertEqual(flow["transition_candidate_count"], count - 1)
                self.assertEqual(flow["full_path_pair_count"], count - 1)
                self.assertEqual(flow["full_path_pair_coverage"], 1.0)
                self.assertEqual(flow["morphology_opportunity_count"], count - 2)
                self.assertEqual(flow["directional_pair_count"], count - 2)
                self.assertEqual(flow["directional_pair_coverage"], 1.0)
                self.assertEqual(flow["strict_pair_count"], 0)
                self.assertEqual(flow["broad_longest_chain_notes"], count)
                self.assertEqual(flow["coherence_gate"], 0.0 if count == 3 else 1.0)

    def test_unqualified_flow_route_retains_beta5_axis_exactly(self):
        points = [(100, 100), (200, 100), (200, 200)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "three-notes.osu"
            path.write_text(circle_chain_text(points), encoding="utf-8")
            old_rows, old_features, old_metadata = previous.extract_from_path(
                str(path)
            )
            new_rows, new_features, new_metadata = beta.extract_from_path(str(path))
            old_components, _ = previous.extract_components(
                old_rows,
                old_features,
                old_metadata["difficulty"],
            )
            new_components, _ = beta.extract_components(
                new_rows,
                new_features,
                new_metadata["difficulty"],
                source_local_signal_version=new_metadata["local_signal_version"],
            )
            old_components["v091_nm_star_anchor"] = 7.0
            new_components["v091_nm_star_anchor"] = 7.0
            checksum = "sha256:" + "6" * 64
            calibration = mini_calibration()
            old_output = previous.analyze_components(
                checksum=checksum,
                components=old_components,
                calibration=calibration,
            )
            new_output = beta.analyze_components(
                checksum=checksum,
                components=new_components,
                calibration=calibration,
            )

        self.assertEqual(
            new_output["axes"]["flow_aim"],
            old_output["axes"]["flow_aim"],
        )
        self.assertEqual(
            new_output["diagnostics"]["beta6_aim_routing_activation"][
                "flow_aim"
            ],
            0.0,
        )
        self.assertNotIn(
            "flow_aim",
            new_output["diagnostics"]["beta6_replaced_axes"],
        )

    def test_partial_jump_coverage_blends_with_beta5(self):
        temp, _, new = self._extract(compound=False)
        self.addCleanup(temp.cleanup)
        rows, features, metadata = new
        components, _ = beta.extract_components(
            rows,
            features,
            metadata["difficulty"],
            source_local_signal_version=metadata["local_signal_version"],
        )
        base_components, _ = previous.extract_components(
            list(rows),
            features,
            metadata["difficulty"],
        )
        components["v091_nm_star_anchor"] = 7.0
        base_components["v091_nm_star_anchor"] = 7.0

        partial_rows = [dict(rows[0]), dict(rows[1])]
        invalid = dict(rows[1])
        for key in (
            "ls.minimum_jump_distance_cs_normalised",
            "ls.jump_distance_raw_px",
            "ls.lazy_jump_distance_cs_normalised",
            "ls.adjusted_delta_time_ms",
            "ls.slider_aware_angle_rad",
        ):
            invalid[key] = None
        partial_rows.extend(dict(invalid) for _ in range(1000))
        partial_measure = beta.routing.aim_routing_measure(
            partial_rows,
            source_local_signal_version=beta.EXPECTED_LOCAL_SIGNAL_VERSION,
        )
        components["beta6_aim_routing"] = partial_measure

        checksum = "sha256:" + "6" * 64
        calibration = mini_calibration()
        baseline = previous.analyze_components(
            checksum=checksum,
            components=base_components,
            calibration=calibration,
        )
        routed = beta.analyze_components(
            checksum=checksum,
            components=components,
            calibration=calibration,
        )

        activation = partial_measure["jump"]["routing_activation"]
        incoming = baseline["axes"]["jump_aim"]["demand_star_equivalent"]
        candidate = routed["diagnostics"]["beta6_aim_routing_candidate"][
            "jump_aim"
        ]
        expected = (1.0 - activation) * incoming + activation * candidate
        self.assertLess(activation, 0.002)
        self.assertAlmostEqual(
            routed["axes"]["jump_aim"]["demand_star_equivalent"],
            expected,
        )
        self.assertLess(
            abs(
                routed["axes"]["jump_aim"]["demand_star_equivalent"]
                - incoming
            ),
            0.01,
        )

    def test_partial_flow_coverage_blends_with_beta5(self):
        points = [
            (100, 100),
            (200, 100),
            (200, 200),
            (100, 200),
            (100, 100),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "flow.osu"
            path.write_text(circle_chain_text(points), encoding="utf-8")
            rows, features, metadata = beta.extract_from_path(str(path))
            components, _ = beta.extract_components(
                rows,
                features,
                metadata["difficulty"],
                source_local_signal_version=metadata["local_signal_version"],
            )
            base_components, _ = previous.extract_components(
                list(rows),
                features,
                metadata["difficulty"],
            )

            partial_rows = [dict(item) for item in rows]
            invalid = dict(rows[-1])
            for key in (
                "ls.lazy_jump_distance_cs_normalised",
                "ls.adjusted_delta_time_ms",
                "ls.slider_aware_angle_rad",
            ):
                invalid[key] = None
            partial_rows.extend(dict(invalid) for _ in range(1000))
            partial_measure = beta.routing.aim_routing_measure(
                partial_rows,
                source_local_signal_version=beta.EXPECTED_LOCAL_SIGNAL_VERSION,
            )
            components["beta6_aim_routing"] = partial_measure
            components["v091_nm_star_anchor"] = 7.0
            base_components["v091_nm_star_anchor"] = 7.0

            checksum = "sha256:" + "6" * 64
            calibration = mini_calibration()
            baseline = previous.analyze_components(
                checksum=checksum,
                components=base_components,
                calibration=calibration,
            )
            routed = beta.analyze_components(
                checksum=checksum,
                components=components,
                calibration=calibration,
            )

        activation = partial_measure["flow"]["routing_activation"]
        incoming = baseline["axes"]["flow_aim"]["demand_star_equivalent"]
        candidate = routed["diagnostics"]["beta6_aim_routing_candidate"][
            "flow_aim"
        ]
        expected = (1.0 - activation) * incoming + activation * candidate
        self.assertLess(activation, 0.005)
        self.assertGreater(activation, 0.0)
        self.assertAlmostEqual(
            routed["axes"]["flow_aim"]["demand_star_equivalent"],
            expected,
        )
        self.assertLess(
            abs(routed["axes"]["flow_aim"]["demand_star_equivalent"] - incoming),
            abs(candidate - incoming),
        )

    def test_early_mod_failures_still_require_exact_beta6_component(self):
        for mods in (["DT", "HT"], ["FL"]):
            with self.subTest(mods=mods):
                with self.assertRaisesRegex(ValueError, "component must be a dict"):
                    beta.analyze_components(
                        checksum="sha256:" + "6" * 64,
                        requested_mods=mods,
                        components={
                            "beta6_source_local_signal_version": "0.4.0"
                        },
                        calibration=mini_calibration(),
                    )

    def test_beta6_is_opt_in_and_stable_default_remains_selected(self):
        self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
        self.assertIs(release.runtime_model("v010-beta5"), previous)
        self.assertIs(release.runtime_model("v010-beta6"), beta)

    def test_runtime_environment_can_opt_in_without_changing_default(self):
        missing_selector = ROOT / "tmp" / "does-not-exist-beta6-test.json"
        with mock.patch.object(
            release,
            "RUNTIME_SELECTION_PATH",
            missing_selector,
        ), mock.patch.dict(
            os.environ,
            {"SKILL_PROFILER_ALGORITHM": ""},
        ):
            self.assertEqual(release.default_algorithm(), "v100")
            with mock.patch.dict(
                os.environ,
                {"SKILL_PROFILER_ALGORITHM": "v010-beta6"},
            ):
                self.assertEqual(release.default_algorithm(), "v010-beta6")

    def test_cli_can_explicitly_select_beta6(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            map_path = root / "map.osu"
            map_path.write_text(map_text(compound=False), encoding="utf-8")
            calibration_dir = root / "calibration"
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
                        str(map_path),
                        "--calibration-dir",
                        str(calibration_dir),
                        "--algorithm",
                        "v010-beta6",
                        "--star-anchor",
                        "7.0",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["identity"]["map_demand_version"], "0.10.0-beta.6")
            self.assertEqual(payload["identity"]["local_signal_version"], "0.4.0")

    def test_restart_entrypoint_knows_beta6_but_keeps_stable_default(self):
        script = (ROOT / "tools" / "restart-skill-profiler.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("'v010-beta6'", script)
        self.assertIn("'v010-beta6' = '0.10.0-beta.6'", script)
        self.assertIn("$Algorithm = 'v100'", script)
        self.assertIn("$previousAlgorithm = 'v100'", script)
        self.assertIn("Start-Profiler $previousAlgorithm | Out-Null", script)


if __name__ == "__main__":
    unittest.main()

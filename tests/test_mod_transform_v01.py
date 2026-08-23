"""Tests for pre-extraction Map Demand mod transforms."""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for path in (TOOLS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01.hidden_v01 import hidden_pressure  # noqa: E402
from map_demand_v01.mod_context_v01 import normalize_mods  # noqa: E402
from map_demand_v01.mod_transform_v01 import (  # noqa: E402
    scale_local_difficulty_windows,
    transform_beatmap,
    transform_context_matches,
)
from map_demand_v01.model import (  # noqa: E402
    analyze_components,
    extract_components,
    extract_from_path,
)
from osu_skill_profiler.parser.osu_parser import parse_osu  # noqa: E402


MAP_TEXT = (
    "osu file format v14\n"
    "[General]\nMode:0\n"
    "[Metadata]\nTitle:T\nArtist:A\nCreator:C\nVersion:V\n"
    "[Difficulty]\n"
    "HPDrainRate:6\nCircleSize:4\nOverallDifficulty:8\nApproachRate:9\n"
    "SliderMultiplier:1.4\nSliderTickRate:1\n"
    "[TimingPoints]\n0,500,4,2,1,100,1,0\n"
    "[HitObjects]\n"
    "64,96,1000,1,0\n"
    "128,120,1500,2,0,B|128:200,1,100\n"
    "256,192,2500,8,0,3000\n"
)


def _calibration() -> dict:
    distributions = {}
    for axis in C.AXIS_ORDER:
        for signal in C.AXIS_META[axis]["signals"]:
            distributions[signal] = [0.0, 0.25, 0.5, 1.0, 10.0, 100.0]
    return {"calibration_id": "mod-transform-test", "distributions": distributions}


class PureTransformTests(unittest.TestCase):
    def test_dt_scales_timeline_red_timing_and_spinner(self):
        source = parse_osu(MAP_TEXT)
        transformed, context = transform_beatmap(source, normalize_mods("DT"))
        self.assertEqual(context["status"], "APPLIED")
        self.assertTrue(context["analysis_ready"])
        self.assertEqual(context["applied_mods"], ["DT"])
        self.assertAlmostEqual(transformed.hit_objects[0].time_ms, 1000.0 / 1.5)
        self.assertAlmostEqual(transformed.hit_objects[1].time_ms, 1000.0)
        self.assertAlmostEqual(transformed.hit_objects[2].spinner_end_ms, 2000.0)
        self.assertAlmostEqual(transformed.timing_points[0].beat_length_ms, 500.0 / 1.5)
        self.assertAlmostEqual(transformed.timing_points[0].bpm, 180.0)
        # Source is immutable and remains untouched.
        self.assertEqual(source.hit_objects[0].time_ms, 1000.0)
        self.assertEqual(source.timing_points[0].beat_length_ms, 500.0)

    def test_ht_scales_timeline_in_opposite_direction(self):
        source = parse_osu(MAP_TEXT)
        transformed, context = transform_beatmap(source, normalize_mods("DC"))
        self.assertEqual(context["effective_mods"], ["HT"])
        self.assertAlmostEqual(transformed.hit_objects[0].time_ms, 1000.0 / 0.75)
        self.assertAlmostEqual(transformed.timing_points[0].bpm, 90.0)

    def test_hr_applies_standard_difficulty_and_vertical_reflection(self):
        source = parse_osu(MAP_TEXT)
        transformed, context = transform_beatmap(source, normalize_mods("HR"))
        self.assertAlmostEqual(transformed.difficulty["HPDrainRate"], 8.4)
        self.assertEqual(transformed.difficulty["OverallDifficulty"], 10.0)
        self.assertEqual(transformed.difficulty["ApproachRate"], 10.0)
        self.assertAlmostEqual(transformed.difficulty["CircleSize"], 5.2)
        self.assertEqual(transformed.hit_objects[0].y, 288.0)
        self.assertEqual(transformed.hit_objects[1].slider_points[0], (128.0, 184.0))
        self.assertTrue(context["geometry_reflected"])

    def test_ez_halves_difficulty_and_materializes_legacy_ar(self):
        source = parse_osu(MAP_TEXT.replace("ApproachRate:9\n", ""))
        transformed, context = transform_beatmap(source, normalize_mods("EZ"))
        self.assertEqual(transformed.difficulty["HPDrainRate"], 3.0)
        self.assertEqual(transformed.difficulty["CircleSize"], 2.0)
        self.assertEqual(transformed.difficulty["OverallDifficulty"], 4.0)
        self.assertEqual(transformed.difficulty["ApproachRate"], 4.0)
        self.assertTrue(context["legacy_ar_fallback_applied"])

    def test_hd_is_ready_while_fl_remains_blocked(self):
        source = parse_osu(MAP_TEXT)
        for mods in ("HD", "HDDT"):
            with self.subTest(mods=mods):
                transformed, context = transform_beatmap(source, normalize_mods(mods))
                self.assertTrue(context["analysis_ready"])
                self.assertEqual(context["status"], "APPLIED")
                self.assertEqual(transformed.difficulty, source.difficulty)
        for mods in ("FL", "HDFL"):
            with self.subTest(mods=mods):
                _, context = transform_beatmap(source, normalize_mods(mods))
                self.assertFalse(context["analysis_ready"])
                self.assertNotEqual(context["status"], "APPLIED")

    def test_local_ar_od_windows_scale_with_clock_rate(self):
        rows = [
            {
                "ls.preempt_ms": 450.0,
                "ls.fade_in_ms": 400.0,
                "ls.hit_window_great_ms": 39.0,
                "other": 7,
            }
        ]
        scaled = scale_local_difficulty_windows(rows, 1.5)
        self.assertEqual(rows[0]["ls.preempt_ms"], 450.0)
        self.assertEqual(scaled[0]["ls.preempt_ms"], 300.0)
        self.assertAlmostEqual(scaled[0]["ls.hit_window_great_ms"], 26.0)
        self.assertEqual(scaled[0]["other"], 7)

    def test_hidden_pressure_is_bounded_and_monotone_in_preempt_density_velocity(self):
        def pressure(preempt: float, density: float, jump: float) -> float:
            value = hidden_pressure(
                [
                    {
                        "ls.object_type": "circle",
                        "ls.preempt_ms": preempt,
                        "ls.adjusted_delta_time_ms": 100.0,
                        "ls.lazy_jump_distance_cs_normalised": jump,
                    }
                ],
                {"section.density_per_s_p95": density},
            )
            self.assertIsNotNone(value)
            return float(value)

        base = pressure(450.0, 1.0, 10.0)
        self.assertGreaterEqual(pressure(900.0, 1.0, 10.0), base)
        self.assertGreaterEqual(pressure(450.0, 8.0, 10.0), base)
        self.assertGreaterEqual(pressure(450.0, 1.0, 1000.0), base)
        self.assertTrue(0.0 <= base <= 1.0)


class ExtractionIntegrationTests(unittest.TestCase):
    def _extract(self, mods: str):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "map.osu"
            path.write_text(MAP_TEXT, encoding="utf-8")
            return extract_from_path(str(path), requested_mods=mods)

    def test_dt_reextracts_features_and_local_signals_on_modded_timeline(self):
        nm_rows, nm_features, _ = self._extract("NM")
        dt_rows, dt_features, metadata = self._extract("NC")
        self.assertAlmostEqual(
            dt_rows[1]["ls.delta_time_ms"], nm_rows[1]["ls.delta_time_ms"] / 1.5
        )
        self.assertAlmostEqual(
            dt_rows[0]["ls.preempt_ms"], nm_rows[0]["ls.preempt_ms"] / 1.5
        )
        self.assertAlmostEqual(
            dt_features["temporal.map_duration_ms"],
            nm_features["temporal.map_duration_ms"] / 1.5,
        )
        self.assertTrue(
            transform_context_matches(
                metadata["mod_transform_context"], metadata["mod_context"]
            )
        )

    def test_hrdt_combination_can_reach_axis_analysis(self):
        rows, features, metadata = self._extract("HRDT")
        transform = metadata["mod_transform_context"]
        components, _ = extract_components(
            rows,
            features,
            difficulty=metadata["difficulty"],
            clock_rate=transform["clock_rate"],
        )
        output = analyze_components(
            checksum="sha256:hrdt",
            requested_mods="HRDT",
            components=components,
            calibration=_calibration(),
            applied_mod_context=transform,
        )
        self.assertEqual(output["status"], "OK")
        self.assertEqual(output["identity"]["effective_mods"], ["HR", "DT"])
        self.assertEqual(output["identity"]["clock_rate"], 1.5)
        self.assertEqual(output["diagnostics"]["mod_transform_context"]["status"], "APPLIED")
        self.assertTrue(
            all(
                axis["status"] in {"EMITTED", "INSUFFICIENT_EVIDENCE"}
                for axis in output["axes"].values()
            )
        )

    def test_hd_adds_bounded_reading_evidence_and_combines_with_dt(self):
        outputs = {}
        for mods in ("NM", "HD", "HDDT"):
            rows, features, metadata = self._extract(mods)
            transform = metadata["mod_transform_context"]
            components, _ = extract_components(
                rows,
                features,
                difficulty=metadata["difficulty"],
                clock_rate=transform["clock_rate"],
                effective_mods=metadata["mod_context"]["effective_mods"],
            )
            outputs[mods] = analyze_components(
                checksum=f"sha256:{mods}",
                requested_mods=mods,
                components=components,
                calibration=_calibration(),
                applied_mod_context=transform,
            )

        self.assertEqual(outputs["HD"]["status"], "OK")
        self.assertEqual(outputs["HDDT"]["status"], "OK")
        pressure = outputs["HD"]["diagnostics"]["components"]["reading_hidden_pressure"]
        self.assertTrue(0.0 <= pressure <= 1.0)
        self.assertGreaterEqual(
            outputs["HD"]["axes"]["reading"]["score"],
            outputs["NM"]["axes"]["reading"]["score"],
        )
        evidence = outputs["HD"]["axes"]["reading"]["evidence"]
        self.assertTrue(
            any(item.get("evidence_tag") == "HEURISTIC_PROXY_INSPIRED_BY_PPY_HIDDEN" for item in evidence)
        )

    def test_transform_context_cannot_be_reused_for_different_mods(self):
        rows, features, metadata = self._extract("DT")
        transform = metadata["mod_transform_context"]
        components, _ = extract_components(
            rows,
            features,
            difficulty=metadata["difficulty"],
            clock_rate=transform["clock_rate"],
        )
        output = analyze_components(
            checksum="sha256:mismatch",
            requested_mods="HT",
            components=components,
            calibration=_calibration(),
            applied_mod_context=transform,
        )
        self.assertEqual(output["status"], "UNSUPPORTED_MOD_STATE")
        self.assertTrue(all(axis["score"] is None for axis in output["axes"].values()))

    def test_hd_transform_without_required_signal_fails_closed(self):
        rows, features, metadata = self._extract("HD")
        transform = metadata["mod_transform_context"]
        # Deliberately omit effective_mods so extraction cannot create the HD
        # component, then prove the transform receipt alone is insufficient.
        components, _ = extract_components(
            rows,
            features,
            difficulty=metadata["difficulty"],
            clock_rate=transform["clock_rate"],
        )
        output = analyze_components(
            checksum="sha256:hd-missing-signal",
            requested_mods="HD",
            components=components,
            calibration=_calibration(),
            applied_mod_context=transform,
        )
        self.assertEqual(output["status"], "UNSUPPORTED_MOD_STATE")
        self.assertTrue(all(axis["score"] is None for axis in output["axes"].values()))

    def test_effective_ar_window_is_divided_by_clock_rate(self):
        rows, features, metadata = self._extract("DT")
        transform = metadata["mod_transform_context"]
        components, _ = extract_components(
            rows,
            features,
            difficulty=metadata["difficulty"],
            clock_rate=transform["clock_rate"],
        )
        self.assertTrue(math.isfinite(float(components["reading_preempt_median_ms"])))
        self.assertAlmostEqual(
            components["reading_preempt_median_ms"], rows[0]["ls.preempt_ms"]
        )


if __name__ == "__main__":
    unittest.main()

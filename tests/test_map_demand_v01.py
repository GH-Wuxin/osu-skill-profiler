"""Tests for the experimental tools/map_demand_v01 package.

Covers corrected precision semantics, identity/calibration, unsupported mod
state, reference-signal leakage gate, property/pathological behavior, strict
finite serialization, and cross-file design consistency.
"""

from __future__ import annotations

import json
import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01.calibration import (  # noqa: E402
    build_calibration,
    load_calibration,
    load_samples,
    make_calibration_id,
)
from map_demand_v01.model import (  # noqa: E402
    analyze_components,
    derive_summaries,
    extract_components,
    high_ar_pressure_ms,
    precision_pressure,
    score_components,
)


def mini_calibration(n: int = 64, seed: int = 7) -> dict:
    rnd = random.Random(seed)
    names: set[str] = set()
    for axis in C.AXIS_ORDER:
        names.update(C.AXIS_META[axis]["signals"])
    distributions = {name: sorted(rnd.uniform(1.0, 100.0) for _ in range(n)) for name in sorted(names)}
    return {"calibration_id": f"mini:{seed}:{n}", "distributions": distributions}


def full_components() -> dict:
    return {
        "jump_aim_strain_p90": 10.0,
        "flow_aim_continuity_share": 0.7,
        "flow_aim_chain_length_p90": 6.0,
        "flow_aim_chain_velocity_p90": 1.0,
        "aim_control_angle_change_p90": 2.0,
        "aim_control_velocity_change_p90": 3.0,
        "spatial_precision_pressure_p90": 50000.0,
        "raw_speed_strain_p90": 5.0,
        "stamina_sustained_ms": 4000.0,
        "stamina_duration_share": 0.2,
        "stamina_density": 3.0,
        "finger_control_interval_entropy": 1.7,
        "finger_control_interval_diversity": 0.02,
        "finger_control_interval_ratio": 1.4,
        "timing_precision_window_pressure": 12.5,
        "reading_preempt_median_ms": 450.0,
        "reading_density": 4.0,
        "reading_visual_change": 0.5,
        "row_counts": {},
    }


def local_row(**overrides) -> dict:
    row = {
        "ls.adjusted_delta_time_ms": 200.0,
        "ls.hit_window_great_ms": 80.0,
        "ls.double_tap_feasibility": 0.2,
        "ls.minimum_jump_distance_cs_normalised": 100.0,
        "ls.minimum_jump_time_ms": 200.0,
        "ls.lazy_jump_distance_cs_normalised": 100.0,
        "ls.slider_aware_angle_rad": math.pi / 2,
        "ls.preempt_ms": 600.0,
    }
    for key, value in overrides.items():
        row["ls." + key] = value
    return row


def feature_block(**overrides) -> dict:
    features = {
        "temporal.longest_dense_section_ms": 4000.0,
        "temporal.map_duration_ms": 100000.0,
        "section.duration_weighted_density_per_s": 3.0,
        "temporal.rhythm_entropy_bits": 1.7,
        "temporal.interval_diversity": 0.02,
        "temporal.interval_ratio_mean": 1.4,
        "section.density_per_s_p95": 4.0,
        "spatial.direction_change_ratio_ge_90": 0.5,
    }
    features.update(overrides)
    return features


class ContractTests(unittest.TestCase):
    def test_identity_differs_for_mods_calibration_algorithm(self):
        base = C.make_identity(beatmap_checksum="sha256:a", calibration_id="cal:1")
        mods = C.make_identity(beatmap_checksum="sha256:a", effective_mods=["DT"], calibration_id="cal:1")
        cal = C.make_identity(beatmap_checksum="sha256:a", calibration_id="cal:2")
        alg = C.make_identity(beatmap_checksum="sha256:a", calibration_id="cal:1", algorithm_id="OTHER")
        keys = [C.identity_cache_key(x) for x in (base, mods, cal, alg)]
        self.assertEqual(len(keys), len(set(keys)))

    def test_identity_is_stable_and_complete(self):
        identity = C.make_identity(beatmap_checksum="sha256:b", calibration_id="cal:1")
        self.assertEqual(identity["ruleset"], "osu")
        self.assertEqual(identity["effective_mods"], [])
        self.assertEqual(identity["clock_rate"], 1.0)
        self.assertEqual(identity["feature_version"], "0.2.0")
        self.assertEqual(identity["local_signal_version"], "0.3.0")
        self.assertEqual(identity["map_demand_version"], "0.6.0")
        self.assertEqual(
            C.identity_cache_key(identity), C.identity_cache_key(dict(identity))
        )

    def test_strict_json_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            C.strict_json_dumps({"x": float("nan")})

    def test_quantile_rank_monotonic_and_endpoints(self):
        dist = [1.0, 2.0, 2.0, 5.0]
        self.assertEqual(C.quantile_rank(dist, 0.0), 0.0)
        self.assertEqual(C.quantile_rank(dist, 1.0), 0.125)
        self.assertEqual(C.quantile_rank(dist, 2.0), 0.5)
        self.assertEqual(C.quantile_rank(dist, 9.0), 1.0)
        ranks = [C.quantile_rank(dist, x) for x in (-10.0, 1.0, 2.0, 5.0, 10.0)]
        self.assertEqual(ranks, sorted(ranks))

    def test_quantile_rank_keeps_large_zero_ties_at_true_floor(self):
        self.assertEqual(C.quantile_rank([0.0, 0.0, 0.0, 1.0], 0.0), 0.0)

    def test_percentile_linear_matches_production_definition(self):
        self.assertAlmostEqual(C.percentile_linear([1.0, 2.0, 3.0], 0.9), 2.8, places=12)


class PrecisionPropertyTests(unittest.TestCase):
    def test_same_distance_less_time_not_lower_pressure(self):
        for distance in (1.0, 50.0, 200.0, 5000.0):
            for t1, t2 in ((500.0, 200.0), (200.0, 50.0), (50.0, 25.0)):
                p1 = precision_pressure(distance, t1)
                p2 = precision_pressure(distance, t2)
                self.assertGreaterEqual(p2, p1)
                self.assertTrue(math.isfinite(p2))

    def test_same_time_more_distance_not_lower_pressure(self):
        for t in (100.0, 500.0):
            for d1, d2 in ((10.0, 100.0), (100.0, 1000.0)):
                p1 = precision_pressure(d1, t)
                p2 = precision_pressure(d2, t)
                self.assertGreaterEqual(p2, p1)
                self.assertTrue(math.isfinite(p2))

    def test_human_time_boundary_saturates_not_zero(self):
        distance = 100.0
        human = math.log2(distance / 100.0 + 1.0) * 5.0
        at_boundary = precision_pressure(distance, human)
        below_boundary = precision_pressure(distance, human - 1.0)
        just_above = precision_pressure(distance, human + 2.0)
        self.assertEqual(at_boundary, C.PRECISION_PRESSURE_CAP)
        self.assertEqual(below_boundary, C.PRECISION_PRESSURE_CAP)
        self.assertLess(just_above, C.PRECISION_PRESSURE_CAP)
        self.assertGreater(just_above, 0.0)

    def test_zero_distance_is_zero_pressure(self):
        self.assertEqual(precision_pressure(0.0, 25.0), 0.0)
        self.assertEqual(precision_pressure(-5.0, 25.0), 0.0)

    def test_extract_components_ignores_raw_cs(self):
        rows = [local_row()] * 5
        f1 = feature_block()
        f2 = feature_block()
        f2["difficulty.CS"] = 2.0
        c1, _ = extract_components(rows, f1)
        c2, _ = extract_components(rows, f2)
        self.assertEqual(
            c1["spatial_precision_pressure_p90"],
            c2["spatial_precision_pressure_p90"],
        )


class SpeedPropertyTests(unittest.TestCase):
    def test_shorter_delta_not_lower_speed_component(self):
        def speed(dt: float) -> float:
            components, _ = extract_components(
                [local_row(adjusted_delta_time_ms=dt)] * 10, feature_block()
            )
            self.assertIsNotNone(components["raw_speed_strain_p90"])
            return float(components["raw_speed_strain_p90"])

        self.assertGreaterEqual(speed(100.0), speed(200.0))
        self.assertGreaterEqual(speed(25.0), speed(50.0))

    def test_double_tap_feasibility_penalty_direction(self):
        def speed(feas: float) -> float:
            components, _ = extract_components(
                [local_row(double_tap_feasibility=feas)] * 10, feature_block()
            )
            return float(components["raw_speed_strain_p90"])

        self.assertGreaterEqual(speed(0.0), speed(1.0))

    def test_missing_hit_window_abstains_speed(self):
        components, _ = extract_components(
            [local_row(hit_window_great_ms=None)] * 10, feature_block()
        )
        self.assertIsNone(components["raw_speed_strain_p90"])


class AtomicSignalPropertyTests(unittest.TestCase):
    def test_stable_continuous_chain_favors_flow_over_angle_change(self):
        stable = [local_row(slider_aware_angle_rad=math.pi) for _ in range(8)]
        alternating = [
            local_row(slider_aware_angle_rad=(math.pi if index % 2 else 0.0))
            for index in range(8)
        ]
        stable_components, _ = extract_components(stable, feature_block())
        alternating_components, _ = extract_components(alternating, feature_block())
        self.assertGreater(
            float(stable_components["flow_aim_continuity_share"]),
            float(alternating_components["flow_aim_continuity_share"]),
        )
        self.assertLess(
            float(stable_components["aim_control_angle_change_p90"]),
            float(alternating_components["aim_control_angle_change_p90"]),
        )

    def test_velocity_variation_increases_aim_control_not_jump_definition(self):
        constant = [local_row(lazy_jump_distance_cs_normalised=100.0) for _ in range(8)]
        variable = [
            local_row(lazy_jump_distance_cs_normalised=(20.0 if index % 2 else 180.0))
            for index in range(8)
        ]
        constant_components, _ = extract_components(constant, feature_block())
        variable_components, _ = extract_components(variable, feature_block())
        self.assertGreater(
            float(variable_components["aim_control_velocity_change_p90"]),
            float(constant_components["aim_control_velocity_change_p90"]),
        )

    def test_narrower_hit_window_increases_timing_precision(self):
        wide, _ = extract_components(
            [local_row(hit_window_great_ms=100.0) for _ in range(4)], feature_block()
        )
        narrow, _ = extract_components(
            [local_row(hit_window_great_ms=50.0) for _ in range(4)], feature_block()
        )
        self.assertGreater(
            float(narrow["timing_precision_window_pressure"]),
            float(wide["timing_precision_window_pressure"]),
        )

    def test_summaries_are_display_only_and_do_not_replace_atomic_axes(self):
        axes, _, _ = score_components(full_components(), mini_calibration())
        summaries = derive_summaries(axes)
        self.assertEqual(set(summaries), set(C.SUMMARY_ORDER))
        self.assertEqual(set(axes), set(C.AXIS_ORDER))
        self.assertTrue(all(item["status"] == "EMITTED" for item in summaries.values()))
        expected = sum(axes[a]["score"] for a in C.AXIS_ORDER) / len(C.AXIS_ORDER)
        self.assertAlmostEqual(summaries["overall_demand"]["score"], expected)


class AxisScoringTests(unittest.TestCase):
    def test_all_axes_emit_with_full_components(self):
        axes, _, abstentions = score_components(full_components(), mini_calibration())
        self.assertEqual(abstentions, [])
        for axis in C.AXIS_ORDER:
            self.assertEqual(axes[axis]["status"], "EMITTED")
            self.assertTrue(0.0 <= axes[axis]["score"] <= 1.0)

    def test_missing_signal_abstains_not_zero(self):
        components = full_components()
        components["raw_speed_strain_p90"] = None
        axes, _, abstentions = score_components(components, mini_calibration())
        self.assertEqual(axes["raw_speed"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(axes["raw_speed"]["score"])
        self.assertTrue(any(a["axis"] == "raw_speed" for a in abstentions))

    def test_stamina_sustained_increase_not_lower_score(self):
        cal = mini_calibration()
        c1 = full_components()
        c2 = dict(c1)
        c2["stamina_sustained_ms"] = c1["stamina_sustained_ms"] + 10000.0
        a1, _, _ = score_components(c1, cal)
        a2, _, _ = score_components(c2, cal)
        self.assertGreaterEqual(a2["stamina"]["score"], a1["stamina"]["score"])

    def test_high_ar_reading_monotone_in_lower_preempt(self):
        self.assertGreaterEqual(high_ar_pressure_ms(300.0), high_ar_pressure_ms(450.0))
        self.assertGreaterEqual(high_ar_pressure_ms(450.0), high_ar_pressure_ms(499.0))
        self.assertEqual(high_ar_pressure_ms(600.0), 0.0)
        c1 = full_components()
        c2 = dict(c1)
        c2["reading_preempt_median_ms"] = 300.0
        a1, _, _ = score_components(c1, mini_calibration())
        a2, _, _ = score_components(c2, mini_calibration())
        self.assertGreaterEqual(a2["reading"]["score"], a1["reading"]["score"])

    def test_reading_visual_change_uses_direct_ratio(self):
        c1 = full_components()
        c2 = dict(c1)
        c2["reading_visual_change"] = c1["reading_visual_change"] + 0.2
        a1, _, _ = score_components(c1, mini_calibration())
        a2, _, _ = score_components(c2, mini_calibration())
        self.assertGreaterEqual(a2["reading"]["score"], a1["reading"]["score"])

    def test_legacy_capped_star_scale_remains_readable(self):
        calibration = mini_calibration()
        calibration["demand_scale"] = {
            "method": "TEST_STAR_SCALE",
            "cap_stars": 10.0,
            "nm_stars": [0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
        }
        axes, _, _ = score_components(full_components(), calibration)
        for axis in C.AXIS_ORDER:
            self.assertAlmostEqual(
                axes[axis]["score"], axes[axis]["demand_star_equivalent"] / 10.0
            )
            self.assertLessEqual(axes[axis]["demand_star_equivalent"], 10.0)
            self.assertEqual(axes[axis]["scale_method"], "TEST_STAR_SCALE")
            self.assertIn("percentile_rank", axes[axis])

    def test_unbounded_star_scale_can_exceed_ten(self):
        calibration = mini_calibration()
        calibration["demand_scale"] = {
            "method": "TEST_UNBOUNDED_STAR_SCALE",
            "score_normalizer_stars": 10.0,
            "hard_cap_stars": None,
            "nm_stars": [0.0, 2.0, 4.0, 6.0, 8.0, 12.0],
        }
        components = full_components()
        components["jump_aim_strain_p90"] = 1.0e6
        axes, _, _ = score_components(components, calibration)
        self.assertEqual(axes["jump_aim"]["demand_star_equivalent"], 12.0)
        self.assertEqual(axes["jump_aim"]["score"], 1.2)

    def test_robust_extreme_tail_ignores_single_absurd_star_outlier(self):
        calibration = mini_calibration()
        calibration["demand_scale"] = {
            "method": "TEST_ROBUST_UNBOUNDED_STAR_SCALE",
            "score_normalizer_stars": 10.0,
            "hard_cap_stars": None,
            "extreme_tail": {
                "method": "LOG_SURVIVAL_LINEAR_V01",
                "lower_quantile": 0.999,
                "upper_quantile": 0.9999,
                "minimum_survival_count": 0.5,
            },
            "nm_stars": [index / 1000.0 for index in range(10001)] + [1000.0],
        }
        components = full_components()
        components["jump_aim_strain_p90"] = 1.0e6
        axes, _, _ = score_components(components, calibration)
        stars = axes["jump_aim"]["demand_star_equivalent"]
        self.assertGreater(stars, 10.0)
        self.assertLess(stars, 20.0)

    def test_flow_morphology_cannot_score_without_chain_velocity(self):
        calibration = mini_calibration()
        calibration["distributions"].update(
            {
                "flow_aim_continuity_share": [0.0, 1.0],
                "flow_aim_chain_length_p90": [0.0, 100.0],
                "flow_aim_chain_velocity_p90": [0.0, 1.0],
            }
        )
        components = full_components()
        components.update(
            flow_aim_continuity_share=1.0,
            flow_aim_chain_length_p90=100.0,
            flow_aim_chain_velocity_p90=0.0,
        )
        axes, _, _ = score_components(components, calibration)
        self.assertEqual(axes["flow_aim"]["percentile_rank"], 0.0)

    def test_density_alone_cannot_create_high_reading(self):
        calibration = mini_calibration()
        calibration["distributions"].update(
            {
                "reading_high_ar_pressure": [0.0, 1.0],
                "reading_density": [0.0, 1.0],
                "reading_visual_change": [0.0, 1.0],
            }
        )
        components = full_components()
        components.update(
            reading_preempt_median_ms=600.0,
            reading_density=2.0,
            reading_visual_change=0.0,
        )
        axes, _, _ = score_components(components, calibration)
        self.assertLess(axes["reading"]["percentile_rank"], 0.20)


class UnsupportedAndPathologicalTests(unittest.TestCase):
    def test_unsupported_mods_never_silently_nm(self):
        output = analyze_components(
            checksum="sha256:m",
            requested_mods=["DT"],
            components=full_components(),
            calibration=mini_calibration(),
        )
        self.assertEqual(output["status"], "UNSUPPORTED_MOD_STATE")
        for axis in C.AXIS_ORDER:
            self.assertEqual(output["axes"][axis]["status"], "UNSUPPORTED_MOD_STATE")
            self.assertIsNone(output["axes"][axis]["score"])

    def test_empty_and_single_object_do_not_fabricate_scores(self):
        cal = mini_calibration()
        empty_components, _ = extract_components([], {})
        output = analyze_components(
            checksum="sha256:empty", components=empty_components, calibration=cal
        )
        self.assertEqual(output["status"], "OK")
        for axis in C.AXIS_ORDER:
            self.assertEqual(output["axes"][axis]["status"], "INSUFFICIENT_EVIDENCE")
            self.assertIsNone(output["axes"][axis]["score"])

        from osu_skill_profiler.parser.osu_parser import parse_osu
        from osu_skill_profiler.signals.extractor import LocalSignalExtractor

        beatmap = parse_osu(
            "osu file format v14\n"
            "[Difficulty]\nCircleSize:4\nApproachRate:9\nOverallDifficulty:8\n"
            "[HitObjects]\n64,64,1000,1,0\n"
        )
        single_components, _ = extract_components(
            LocalSignalExtractor().extract(beatmap)["objects"], {}
        )
        output2 = analyze_components(
            checksum="sha256:single", components=single_components, calibration=cal
        )
        for axis in C.AXIS_ORDER:
            self.assertIsNone(output2["axes"][axis]["score"])
            self.assertEqual(output2["axes"][axis]["status"], "INSUFFICIENT_EVIDENCE")

    def test_near_simultaneous_is_finite(self):
        rows = [
            local_row(adjusted_delta_time_ms=0.0),
            local_row(adjusted_delta_time_ms=0.0),
            local_row(adjusted_delta_time_ms=0.0),
        ]
        components, warnings = extract_components(rows, feature_block())
        for key in (
            "jump_aim_strain_p90",
            "flow_aim_continuity_share",
            "flow_aim_chain_length_p90",
            "flow_aim_chain_velocity_p90",
            "aim_control_angle_change_p90",
            "aim_control_velocity_change_p90",
            "spatial_precision_pressure_p90",
            "raw_speed_strain_p90",
            "timing_precision_window_pressure",
        ):
            self.assertIsNotNone(components[key])
            self.assertTrue(math.isfinite(float(components[key])))
        self.assertIsNotNone(components["raw_speed_strain_p90"])

    def test_geometry_blocked_rows_abstain_per_object_axes(self):
        blocked = {
            "ls.adjusted_delta_time_ms": None,
            "ls.hit_window_great_ms": None,
            "ls.double_tap_feasibility": None,
            "ls.minimum_jump_distance_cs_normalised": None,
            "ls.minimum_jump_time_ms": None,
            "ls.lazy_jump_distance_cs_normalised": None,
            "ls.slider_aware_angle_rad": None,
            "ls.preempt_ms": None,
            "ls.provenance": "geometry_blocked",
        }
        components, warnings = extract_components([blocked], feature_block())
        for key in (
            "jump_aim_strain_p90",
            "flow_aim_continuity_share",
            "flow_aim_chain_length_p90",
            "flow_aim_chain_velocity_p90",
            "aim_control_angle_change_p90",
            "aim_control_velocity_change_p90",
            "spatial_precision_pressure_p90",
            "raw_speed_strain_p90",
            "timing_precision_window_pressure",
        ):
            self.assertIsNone(components[key])
        self.assertTrue(any("no eligible local rows" in w for w in warnings))

    def test_pathological_finite_features_kept_with_warning(self):
        features = feature_block(
            **{
                "temporal.longest_dense_section_ms": 1.0e10,
                "temporal.map_duration_ms": 1.0e298,
                "section.duration_weighted_density_per_s": 999999999.9999999,
                "section.density_per_s_p95": 999999999.9999999,
            }
        )
        components, warnings = extract_components([local_row()] * 10, features)
        self.assertTrue(math.isfinite(float(components["stamina_sustained_ms"])))
        self.assertTrue(math.isfinite(float(components["stamina_density"])))
        self.assertTrue(any("extreme finite value" in w for w in warnings))

    def test_missing_ar_od_related_signals_abstain(self):
        components, _ = extract_components(
            [local_row(hit_window_great_ms=None, preempt_ms=None)] * 10,
            feature_block(),
        )
        axes, _, _ = score_components(components, mini_calibration())
        self.assertEqual(axes["raw_speed"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(axes["reading"]["status"], "INSUFFICIENT_EVIDENCE")
        output = analyze_components(
            checksum="sha256:no-window",
            components=components,
            calibration=mini_calibration(),
        )
        self.assertEqual(
            output["context"]["accuracy_window"]["status"],
            "INSUFFICIENT_EVIDENCE",
        )

    def test_strict_json_output_round_trip(self):
        output = analyze_components(
            checksum="sha256:ok",
            components=full_components(),
            calibration=mini_calibration(),
        )
        text = C.strict_json_dumps(output, indent=2)
        parsed = json.loads(text)
        self.assertEqual(parsed["status"], "OK")
        self.assertEqual(set(parsed["axes"]), set(C.AXIS_ORDER))
        self.assertIn("calibration_id", parsed["identity"])


class ReferenceGateTests(unittest.TestCase):
    def test_reference_signal_gate_rejects_axis_input(self):
        with self.assertRaises(C.ReferenceSignalLeakageError):
            C.assert_no_reference_signals({"ref.ppy.reading": 1.0}, "axis")

    def test_reference_signal_cannot_enter_axis_path(self):
        old_signals = dict(C.AXIS_META["reading"]["signals"])
        components = full_components()
        components["ref.ppy.reading"] = 1.0
        try:
            C.AXIS_META["reading"]["signals"] = {
                "ref.ppy.reading": old_signals["reading_high_ar_pressure"],
                "reading_density": old_signals["reading_density"],
                "reading_visual_change": old_signals["reading_visual_change"],
            }
            with self.assertRaises(C.ReferenceSignalLeakageError):
                score_components(components, mini_calibration())
        finally:
            C.AXIS_META["reading"]["signals"] = old_signals

    def test_reference_diagnostics_allowed_in_diagnostics_only(self):
        output = analyze_components(
            checksum="sha256:diag",
            components=full_components(),
            calibration=mini_calibration(),
            reference_diagnostics={"ref.ppy.reading": 1.2},
        )
        self.assertEqual(output["diagnostics"]["reference_diagnostics"]["ref.ppy.reading"], 1.2)
        for axis, axis_obj in output["axes"].items():
            for signal in axis_obj["signals"]:
                self.assertFalse(signal.startswith("ref.ppy."))


class CalibrationBuilderTests(unittest.TestCase):
    def _build_mini(self, tmp: Path, feature_payload: str = "x") -> dict:
        local = tmp / "local.jsonl"
        feature = tmp / "feature.jsonl"
        rows = [local_row()] * 4
        features = feature_block()
        with local.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"checksum": "sha256:m", "ok": True, "objects": rows}) + "\n")
        with feature.open("w", encoding="utf-8") as fh:
            fh.write(
                json.dumps({"checksum": "sha256:m", "features": features, "tag": feature_payload})
                + "\n"
            )
        out = tmp / "cal"
        result = build_calibration(
            local_qa_path=local,
            feature_qa_path=feature,
            out_dir=out,
            source_scope="5k",
            write_samples=True,
        )
        return result

    def test_build_load_and_manifest_are_consistent(self):
        import hashlib
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self._build_mini(tmp)
            out = tmp / "cal"
            calibration = load_calibration(out)
            samples = load_samples(out / "calibration_samples.jsonl")
            manifest = json.loads((out / "calibration_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(calibration["calibration_id"], result["calibration_id"])
            self.assertEqual(manifest["calibration_id"], result["calibration_id"])
            self.assertEqual(len(samples), result["map_count"])
            self.assertEqual(calibration["map_count"], result["map_count"])
            for name, values in calibration["distributions"].items():
                self.assertEqual(values, sorted(values))
                self.assertTrue(all(math.isfinite(v) for v in values))
            file_digest = hashlib.sha256((out / "calibration.json").read_bytes()).hexdigest()
            self.assertEqual(manifest["artifacts"]["calibration.json"], file_digest)

    def test_calibration_id_is_source_sensitive(self):
        self.assertNotEqual(
            make_calibration_id(
                feature_sha256="a" * 64, local_sha256="b" * 64, source_scope="5k"
            ),
            make_calibration_id(
                feature_sha256="c" * 64, local_sha256="b" * 64, source_scope="5k"
            ),
        )

    def test_load_calibration_rejects_nonfinite_json(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "calibration.json"
            bad.write_text('{"distributions": {"x": NaN}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_calibration(bad)


class LegacyArSemanticsTests(unittest.TestCase):
    @staticmethod
    def _map_text(difficulty_lines: list[str]) -> str:
        return (
            "osu file format v14\n"
            "[General]\nMode:0\n"
            "[Metadata]\nTitle:T\nArtist:A\nCreator:C\nVersion:V\n"
            "[Difficulty]\n"
            + "\n".join(difficulty_lines)
            + "\n[HitObjects]\n64,64,1000,1,0\n320,64,1500,1,0\n"
        )

    @staticmethod
    def _components(difficulty_lines: list[str]) -> tuple[dict, dict]:
        from osu_skill_profiler.parser.osu_parser import parse_osu
        from osu_skill_profiler.signals.extractor import LocalSignalExtractor

        beatmap = parse_osu(LegacyArSemanticsTests._map_text(difficulty_lines))
        rows = LocalSignalExtractor().extract(beatmap)["objects"]
        components, warnings = extract_components(
            rows, feature_block(), difficulty=beatmap.difficulty
        )
        return components, dict(beatmap.difficulty)

    def test_od_only_falls_back_to_od(self):
        components, difficulty = self._components(
            ["CircleSize:4", "OverallDifficulty:7"]
        )
        self.assertEqual(difficulty["OverallDifficulty"], 7.0)
        self.assertNotIn("ApproachRate", difficulty)
        self.assertEqual(components["reading_effective_ar"], 7.0)
        self.assertEqual(components["reading_ar_provenance"], "LEGACY_AR_FALLBACK_TO_OD")
        self.assertIsNotNone(components["reading_preempt_median_ms"])

    def test_od_followed_by_explicit_ar_wins(self):
        components, difficulty = self._components(
            ["CircleSize:4", "OverallDifficulty:7", "ApproachRate:9"]
        )
        self.assertEqual(components["reading_effective_ar"], 9.0)
        self.assertEqual(components["reading_ar_provenance"], "EXPLICIT_AR")

    def test_explicit_ar_wins_without_od(self):
        components, _ = self._components(["CircleSize:4", "ApproachRate:9"])
        self.assertEqual(components["reading_effective_ar"], 9.0)
        self.assertEqual(components["reading_ar_provenance"], "EXPLICIT_AR")

    def test_neither_ar_nor_od_abstains(self):
        components, _ = self._components(["CircleSize:4"])
        self.assertIsNone(components["reading_effective_ar"])
        self.assertIsNone(components["reading_ar_provenance"])
        self.assertIsNone(components["reading_preempt_median_ms"])
        axes, _, _ = score_components(components, mini_calibration())
        self.assertEqual(axes["reading"]["status"], "INSUFFICIENT_EVIDENCE")

    def test_frozen_local_layer_keeps_missing_preempt(self):
        # Ownership boundary: Local 0.3 is frozen and must still expose
        # preempt=None for OD-only legacy maps; only MapDemand resolves the
        # effective AR above it.
        from osu_skill_profiler.parser.osu_parser import parse_osu
        from osu_skill_profiler.signals.extractor import LocalSignalExtractor

        beatmap = parse_osu(self._map_text(["CircleSize:4", "OverallDifficulty:7"]))
        rows = LocalSignalExtractor().extract(beatmap)["objects"]
        self.assertTrue(all(row["ls.preempt_ms"] is None for row in rows))

    def test_ar_preempt_mirror_matches_production_helper(self):
        from osu_skill_profiler.signals.slider import approach_rate_preempt_ms
        from map_demand_v01.model import _ar_preempt_ms

        for ar in (None, -1.0, 0.0, 2.0, 5.0, 7.5, 9.0, 10.0, 11.0):
            self.assertEqual(_ar_preempt_ms(ar), approach_rate_preempt_ms(ar))


class CrossFileConsistencyTests(unittest.TestCase):
    def test_dependency_classification_consistent_across_docs(self):
        taxonomy = json.loads(
            (ROOT / "docs/SKILL_PROFILER_MVP_TAXONOMY_V01.json").read_text(encoding="utf-8")
        )
        matrix = json.loads(
            (ROOT / "docs/SKILL_PROFILER_PRIOR_ART_MATRIX_V01.json").read_text(encoding="utf-8")
        )
        report = (ROOT / "docs/SKILL_PROFILER_PRIOR_ART_AND_MVP_DESIGN_V01.md").read_text(
            encoding="utf-8"
        )

        deferred = {c["id"]: c for c in taxonomy["deferred_constructs"]}
        self.assertEqual(deferred["accuracy"]["dependency"], ["SCORE_REQUIRED"])
        self.assertEqual(deferred["consistency"]["dependency"], ["MULTI_SCORE_REQUIRED"])
        self.assertEqual(
            deferred["memory_flashlight"]["dependency"],
            ["MOD_SIGNAL_REQUIRED", "LOCAL_SIGNAL_UNSUPPORTED"],
        )
        self.assertEqual(deferred["finger_control"]["dependency"], ["REPLAY_REQUIRED"])
        for axis in taxonomy["taxonomy_axes"]:
            self.assertEqual(axis["dependency"], ["BEATMAP_ONLY"])
            self.assertEqual(axis["layer"], "MAP_DEMAND")

        cm = matrix["construct_matrix"]
        self.assertEqual(cm["accuracy"]["dependency"], ["SCORE_REQUIRED"])
        self.assertEqual(cm["consistency"]["dependency"], ["MULTI_SCORE_REQUIRED"])
        self.assertEqual(
            cm["memory_flashlight"]["dependency"],
            ["MOD_SIGNAL_REQUIRED", "LOCAL_SIGNAL_UNSUPPORTED"],
        )
        self.assertEqual(cm["accuracy"]["replay_required"], False)
        self.assertEqual(cm["memory_flashlight"]["replay_required"], False)

        for phrase in (
            "SCORE_REQUIRED",
            "MULTI_SCORE_REQUIRED",
            "MOD_SIGNAL_REQUIRED",
            "HEURISTIC_PROXY_INSPIRED_BY_OSUSKILLS_HUMAN_TIME",
            "UNSUPPORTED_MOD_STATE",
            "PRECISION_PRESSURE_CAP",
            "calibration_id",
        ):
            self.assertIn(phrase, report)

    def test_corrected_precision_formula_present_and_old_units_absent_as_spec(self):
        report = (ROOT / "docs/SKILL_PROFILER_PRIOR_ART_AND_MVP_DESIGN_V01.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("actual_time_ms = ls.minimum_jump_time_ms", report)
        self.assertIn("human_time_ms = log2(distance_cs / 100 + 1) * 5", report)
        self.assertIn("if gap_ms <= 0:", report)
        # The old /1000 seconds conversion must no longer be part of the code spec.
        self.assertNotIn("human_time = log2(max(distance_cs, 1)/100 + 1) * 5", report)
        self.assertNotIn("actual_time = ls.minimum_jump_time_ms / 1000", report)


if __name__ == "__main__":
    unittest.main()

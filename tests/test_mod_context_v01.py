"""Contract tests for deterministic Map Demand mod normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01.mod_context_v01 import normalize_mods  # noqa: E402
from map_demand_v01.model import analyze_components  # noqa: E402


def _calibration() -> dict:
    distributions = {}
    for axis in C.AXIS_ORDER:
        for signal in C.AXIS_META[axis]["signals"]:
            distributions[signal] = [0.0, 1.0]
    return {"calibration_id": "mod-context-test", "distributions": distributions}


def _components() -> dict:
    values = {}
    for axis in C.AXIS_ORDER:
        for signal in C.AXIS_META[axis]["signals"]:
            values[signal] = 0.5
    return values


class ModNormalizationTests(unittest.TestCase):
    def test_nm_spellings_normalize_to_empty_effective_state(self):
        for value in (None, [], "", "NM", "No Mod", "none"):
            context = normalize_mods(value)
            self.assertEqual(context["status"], "NORMALIZED")
            self.assertEqual(context["analysis_support"], "SUPPORTED")
            self.assertEqual(context["effective_mods"], [])
            self.assertEqual(context["clock_rate"], 1.0)

    def test_aliases_delimiters_compact_forms_and_duplicates(self):
        expected = ["HD", "HR", "DT"]
        cases = (
            ["HD", "HR", "DT"],
            ["dt", "hidden", "hard-rock", "DT"],
            "HD+HR+DT",
            "HD HR DT",
            "HDHRDT",
        )
        for value in cases:
            with self.subTest(value=value):
                context = normalize_mods(value)
                self.assertEqual(context["requested_mods"], expected)
                self.assertEqual(context["effective_mods"], expected)
                self.assertEqual(context["clock_rate"], 1.5)

    def test_nc_and_dc_fold_to_timing_equivalents(self):
        nc = normalize_mods("NC")
        dc = normalize_mods("daycore")
        self.assertEqual(nc["requested_mods"], ["NC"])
        self.assertEqual(nc["effective_mods"], ["DT"])
        self.assertEqual(nc["clock_rate"], 1.5)
        self.assertEqual(nc["alias_folds"], [{"from": "NC", "to": "DT"}])
        self.assertEqual(dc["requested_mods"], ["DC"])
        self.assertEqual(dc["effective_mods"], ["HT"])
        self.assertEqual(dc["clock_rate"], 0.75)

    def test_order_and_alias_equivalence_produce_stable_identity(self):
        first = normalize_mods(["NC", "HD"])
        second = normalize_mods("hidden+nightcore")
        self.assertEqual(first["effective_mods"], second["effective_mods"])
        i1 = C.make_identity(
            beatmap_checksum="sha256:x",
            calibration_id="cal:x",
            effective_mods=first["effective_mods"],
            clock_rate=first["clock_rate"],
        )
        i2 = C.make_identity(
            beatmap_checksum="sha256:x",
            calibration_id="cal:x",
            effective_mods=reversed(second["effective_mods"]),
            clock_rate=second["clock_rate"],
        )
        self.assertEqual(i1, i2)
        self.assertEqual(C.identity_cache_key(i1), C.identity_cache_key(i2))

    def test_conflicts_fail_closed(self):
        for value in ("EZHR", "DTNC", "DTHT", "HTDC", "SDPF", "NMHD"):
            with self.subTest(value=value):
                context = normalize_mods(value)
                self.assertEqual(context["status"], "INVALID")
                self.assertEqual(context["errors"][0]["code"], "MOD_CONFLICT")

    def test_unknown_and_non_string_tokens_fail_closed(self):
        unknown = normalize_mods("HD+ZZ")
        non_string = normalize_mods(["HD", 64])
        self.assertEqual(unknown["errors"][0]["code"], "UNKNOWN_MOD")
        self.assertEqual(unknown["unknown_mods"], ["ZZ"])
        self.assertEqual(non_string["status"], "INVALID")

    def test_neutral_mods_are_preserved_but_do_not_change_demand_identity(self):
        context = normalize_mods(["NF", "SD"])
        self.assertEqual(context["requested_mods"], ["NF", "SD"])
        self.assertEqual(context["neutral_mods"], ["NF", "SD"])
        self.assertEqual(context["effective_mods"], [])
        self.assertEqual(context["analysis_support"], "SUPPORTED")

    def test_fl_is_explicitly_deferred_as_separate_dimension(self):
        context = normalize_mods("FL")
        self.assertEqual(context["status"], "NORMALIZED")
        self.assertEqual(context["analysis_support"], "NOT_IMPLEMENTED")
        self.assertEqual(context["effective_mods"], ["FL"])
        self.assertEqual(context["deferred_mods"], ["FL"])
        self.assertEqual(context["pending_signals"], [])


class ModelIntegrationTests(unittest.TestCase):
    def test_pending_transform_is_identified_but_never_scored_as_nm(self):
        output = analyze_components(
            checksum="sha256:dt",
            requested_mods="nightcore",
            components=_components(),
            calibration=_calibration(),
        )
        self.assertEqual(output["status"], "UNSUPPORTED_MOD_STATE")
        self.assertEqual(output["identity"]["effective_mods"], ["DT"])
        self.assertEqual(output["identity"]["clock_rate"], 1.5)
        context = output["diagnostics"]["mod_context"]
        self.assertEqual(context["requested_mods"], ["NC"])
        self.assertEqual(context["pending_transforms"], ["NC"])
        self.assertTrue(all(axis["score"] is None for axis in output["axes"].values()))

    def test_invalid_combination_has_distinct_status(self):
        output = analyze_components(
            checksum="sha256:bad",
            requested_mods="DT+HT",
            components=_components(),
            calibration=_calibration(),
        )
        self.assertEqual(output["status"], "INVALID_MOD_STATE")
        self.assertEqual(output["warnings"][0]["code"], "MOD_CONFLICT")
        self.assertTrue(
            all(axis["status"] == "INVALID_MOD_STATE" for axis in output["axes"].values())
        )

    def test_neutral_mods_keep_nm_scoring_but_remain_auditable(self):
        output = analyze_components(
            checksum="sha256:nf",
            requested_mods=["NF"],
            components=_components(),
            calibration=_calibration(),
        )
        self.assertEqual(output["status"], "OK")
        self.assertEqual(output["identity"]["effective_mods"], [])
        self.assertEqual(output["diagnostics"]["mod_context"]["neutral_mods"], ["NF"])


if __name__ == "__main__":
    unittest.main()

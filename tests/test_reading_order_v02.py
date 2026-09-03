from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import paired_transition_geometry_v01 as paired  # noqa: E402
from map_demand_v01 import reading_order_v01 as legacy  # noqa: E402
from map_demand_v01 import reading_order_v02 as reading  # noqa: E402
from tests.local_pattern_fixtures import folded, rows_for  # noqa: E402


REAL_UNPLAYABLE_HITSOUNDS = Path(
    r"G:\osu! 20210821\Songs\1737561 Gen Hoshino - Comedy (TV Size)"
    r"\Gen Hoshino - Comedy (TV Size) (hakashii) [unplayable hitsounds].osu"
)


def bundle_for(points=None, intervals=None, *, preempt=900.0):
    points = folded(24) if points is None else points
    intervals = [90.0] * (len(points) - 1) if intervals is None else intervals
    return paired.build_transition_bundle(
        rows_for(points, intervals, preempt=preempt)
    )


class ReadingOrderV02Tests(unittest.TestCase):
    def test_schema_identifies_isolated_simultaneous_publication_semantics(self):
        self.assertEqual(reading.SCHEMA_VERSION, "reading_order_v0.3.0")

    def test_full_coverage_preserves_v1_core_value(self):
        bundle = bundle_for()
        expected = legacy.reading_measure(
            bundle["objects"], paired.predictability(bundle["objects"])
        )
        measure = reading.extract_reading_measure(bundle)

        self.assertEqual(measure["status"], reading.FULL)
        self.assertEqual(measure["coverage"], 1.0)
        self.assertEqual(measure["eligible_count"], bundle["transition_count"])
        self.assertEqual(measure["value"], expected["value"])
        self.assertEqual(measure["winning_section"]["value"], measure["value"])
        self.assertEqual(
            measure["winning_section"]["signals"], expected["signals"]
        )
        self.assertFalse(measure["total_sr_used"])

    def test_empty_and_all_spinner_are_insufficient_not_observed_zero(self):
        empty = reading.extract_reading_measure(
            paired.build_transition_bundle([])
        )
        self.assertEqual(empty["status"], reading.INSUFFICIENT)
        self.assertEqual(empty["reason"], "NO_OBJECTS")
        self.assertIsNone(empty["value"])
        self.assertIsNone(empty["winning_section"])

        spinner_rows = [
            {
                "ls.object_type": "spinner",
                "ls.start_time_ms": 0.0,
                "ls.end_time_ms": 1000.0,
            },
            {
                "ls.object_type": "spinner",
                "ls.start_time_ms": 2000.0,
                "ls.end_time_ms": 3000.0,
            },
        ]
        spinner = reading.extract_reading_measure(
            paired.build_transition_bundle(spinner_rows)
        )
        self.assertEqual(spinner["status"], reading.INSUFFICIENT)
        self.assertEqual(spinner["reason"], "NO_NONSPINNER_OBJECTS")
        self.assertIsNone(spinner["value"])

    def test_missing_ar_and_od_context_is_not_zero_and_resolved_fallback_works(self):
        rows = rows_for(folded(16), [100.0] * 15, preempt=900.0)
        for row in rows:
            row.pop("ls.preempt_ms")

        missing = reading.extract_reading_measure(
            paired.build_transition_bundle(rows)
        )
        self.assertEqual(missing["status"], reading.INSUFFICIENT)
        self.assertEqual(missing["reason"], "MISSING_APPROACH_TIMING_CONTEXT")
        self.assertEqual(missing["coverage"], 0.0)
        self.assertIsNone(missing["value"])
        self.assertGreater(
            missing["signals"]["missing_reasons"]["MISSING_PREEMPT"], 0
        )

        # The extractor owns legacy AR=OD materialisation.  Once a resolved
        # preempt is supplied, Reading itself needs no AR/OD special case.
        resolved = reading.extract_reading_measure(
            paired.build_transition_bundle(rows, resolved_preempt_ms=900.0)
        )
        self.assertEqual(resolved["status"], reading.FULL)
        self.assertIsNotNone(resolved["value"])

    def test_no_valid_decision_is_insufficient(self):
        one_object = bundle_for(points=[(256.0, 192.0)], intervals=[])
        measure = reading.extract_reading_measure(one_object)
        self.assertEqual(measure["status"], reading.INSUFFICIENT)
        self.assertEqual(measure["reason"], "NO_VALID_READING_DECISION")
        self.assertEqual(measure["eligible_count"], 0)
        self.assertIsNone(measure["value"])

    def test_all_simultaneous_group_is_structured_unsupported_not_exception(self):
        rows = rows_for(folded(3), [100.0] * 2, preempt=900.0)
        for row in rows:
            row["ls.start_time_ms"] = 0.0
            row["ls.end_time_ms"] = 0.0
        bundle = paired.build_transition_bundle(rows)
        self.assertGreater(bundle["simultaneous_group_count"], 0)

        measure = reading.extract_reading_measure(bundle)
        self.assertEqual(measure["status"], reading.INSUFFICIENT)
        self.assertEqual(measure["reason"], "UNSUPPORTED_SIMULTANEOUS_ORDER")
        self.assertIsNone(measure["value"])
        self.assertGreater(
            measure["signals"]["missing_reasons"][
                "UNSUPPORTED_SIMULTANEOUS_ORDER"
            ],
            0,
        )

    def test_isolated_simultaneous_group_preserves_other_legal_section(self):
        # Keep the perturbed first section deliberately simple and make the
        # later section the unambiguous Reading peak.
        points = [(80.0 + 4.0 * index, 192.0) for index in range(20)]
        points.extend(folded(40))
        rows = rows_for(points, [90.0] * 59, preempt=900.0)
        # Put a later, independent section beyond the bundle's long-gap
        # boundary.  It is the winning section in the unmodified baseline.
        for row in rows[20:]:
            row["ls.start_time_ms"] += 11000.0
            row["ls.end_time_ms"] += 11000.0
        baseline = reading.extract_reading_measure(
            paired.build_transition_bundle(copy.deepcopy(rows))
        )

        rows[4]["ls.start_time_ms"] = rows[3]["ls.start_time_ms"]
        rows[4]["ls.end_time_ms"] = rows[3]["ls.end_time_ms"]
        isolated = reading.extract_reading_measure(
            paired.build_transition_bundle(rows)
        )

        self.assertEqual(baseline["status"], reading.FULL)
        self.assertEqual(isolated["status"], reading.DEGRADED)
        self.assertEqual(isolated["reason"], "ISOLATED_SIMULTANEOUS_ORDER")
        self.assertLess(isolated["coverage"], 1.0)
        self.assertEqual(isolated["value"], baseline["value"])
        self.assertEqual(
            isolated["winning_section"]["start_ms"],
            baseline["winning_section"]["start_ms"],
        )
        self.assertEqual(
            isolated["winning_section"]["end_ms"],
            baseline["winning_section"]["end_ms"],
        )
        self.assertEqual(
            isolated["signals"]["core_event_count"],
            isolated["eligible_count"],
        )

    def test_coverage_full_degraded_and_below_point_eight_abstains(self):
        rows = rows_for(folded(21), [90.0] * 20, preempt=900.0)

        full_rows = copy.deepcopy(rows)
        full_rows[-1]["v091.start_x_px"] = None
        full = reading.extract_reading_measure(
            paired.build_transition_bundle(full_rows)
        )
        self.assertEqual(full["coverage"], 0.95)
        self.assertEqual(full["status"], reading.FULL)
        self.assertIsNotNone(full["value"])

        degraded_rows = copy.deepcopy(rows)
        degraded_rows[10]["v091.start_x_px"] = None
        degraded = reading.extract_reading_measure(
            paired.build_transition_bundle(degraded_rows)
        )
        self.assertEqual(degraded["coverage"], 0.90)
        self.assertEqual(degraded["status"], reading.DEGRADED)
        self.assertIsNotNone(degraded["value"])
        self.assertEqual(degraded["activation"], degraded["coverage"])

        insufficient_rows = copy.deepcopy(rows)
        for index in (4, 10, 16):
            insufficient_rows[index]["v091.start_x_px"] = None
        insufficient = reading.extract_reading_measure(
            paired.build_transition_bundle(insufficient_rows)
        )
        self.assertLess(insufficient["coverage"], 0.80)
        self.assertEqual(insufficient["status"], reading.INSUFFICIENT)
        self.assertEqual(
            insufficient["reason"], "INSUFFICIENT_DECISION_COVERAGE"
        )
        self.assertIsNone(insufficient["value"])
        self.assertEqual(insufficient["activation"], 0.0)

    def test_hidden_cannot_reduce_reading(self):
        bundle = bundle_for(points=folded(80), intervals=[90.0] * 79, preempt=1100.0)
        nm = reading.extract_reading_measure(bundle)
        hd = reading.extract_reading_measure(bundle, effective_mods=("HD",))
        self.assertEqual(nm["status"], reading.FULL)
        self.assertEqual(hd["status"], reading.FULL)
        self.assertGreaterEqual(hd["value"], nm["value"])
        self.assertEqual(nm["coverage"], hd["coverage"])

    def test_legitimate_extreme_tail_is_finite_and_not_clipped(self):
        bundle = bundle_for(
            points=folded(80), intervals=[75.0] * 79, preempt=1200.0
        )
        measure = reading.extract_reading_measure(bundle)
        self.assertEqual(measure["status"], reading.FULL)
        self.assertGreater(measure["value"], 10.0)
        self.assertTrue(measure["value"] < float("inf"))
        self.assertEqual(measure["winning_section"]["value"], measure["value"])
        self.assertGreater(measure["winning_section"]["support_count"], 0)

    @unittest.skipUnless(
        REAL_UNPLAYABLE_HITSOUNDS.is_file(),
        "local [unplayable hitsounds] beatmap is unavailable",
    )
    def test_real_unplayable_hitsounds_tail_is_supported_not_simultaneous(self):
        from map_demand_v01 import model_v010_beta6 as extractor

        rows, _features, _metadata = extractor.extract_from_path(
            str(REAL_UNPLAYABLE_HITSOUNDS)
        )
        bundle = paired.build_transition_bundle(rows)
        measure = reading.extract_reading_measure(bundle)
        self.assertEqual(bundle["simultaneous_group_count"], 0)
        self.assertEqual(measure["status"], reading.FULL)
        self.assertGreater(measure["value"], 9.0)
        self.assertEqual(measure["coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()

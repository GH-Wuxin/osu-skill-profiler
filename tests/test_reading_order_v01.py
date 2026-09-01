from __future__ import annotations

import copy
import math
import unittest

from map_demand_v01 import local_pattern_geometry as geometry
from map_demand_v01 import reading_order_v01 as reading
from map_demand_v01 import model_v010_beta5 as candidate
from map_demand_v01 import model_v010_beta4 as production
from tests.local_pattern_fixtures import folded, rows_for
from tests.test_map_demand_v01 import mini_calibration


def line(count=80, step=18.0):
    return [(i * step, 192.0) for i in range(count)]


def circle(count=80):
    return [(256 + 100 * math.cos(i * .2), 192 + 100 * math.sin(i * .2))
            for i in range(count)]


def measure(rows, mods=()):
    objects = geometry.objects(rows)
    return reading.reading_measure(objects, geometry.predictability(objects), mods)


class ReadingMechanismTests(unittest.TestCase):
    def test_regular_dense_stream_is_below_same_density_folded_order(self):
        regular = measure(rows_for(line(), [75] * 79, preempt=1100))
        confusing = measure(rows_for(folded(), [75] * 79, preempt=1100))
        self.assertLess(regular["value"], 4)
        self.assertGreater(confusing["value"], regular["value"] + 3)
        self.assertGreater(regular["signals"]["visible_heads"], 4)

    def test_stationary_repeated_stack_is_not_fake_ambiguity(self):
        result = measure(rows_for([(256, 192)] * 80, [75] * 79, preempt=1200))
        self.assertEqual(result["signals"]["order_conflict"], 0)
        self.assertLess(result["value"], 4)

    def test_constant_curvature_and_repeated_cadence_are_learnable(self):
        regular = measure(rows_for(circle(), ([125, 250] * 40)[:79], preempt=1000))
        confusing = measure(rows_for(folded(), ([125, 250] * 40)[:79], preempt=1000))
        self.assertLess(regular["value"], confusing["value"] - 1.5)

    def test_lower_ar_only_raises_a_scene_with_order_evidence(self):
        regular_high = measure(rows_for(line(), [100] * 79, preempt=450))["value"]
        regular_low = measure(rows_for(line(), [100] * 79, preempt=1200))["value"]
        folded_high = measure(rows_for(folded(), [100] * 79, preempt=450))["value"]
        folded_low = measure(rows_for(folded(), [100] * 79, preempt=1200))["value"]
        self.assertLess(regular_low, 4)
        self.assertLess(regular_low - regular_high, 1.2)
        self.assertGreater(folded_low, folded_high + 1)

    def test_long_preempt_on_slow_low_information_map_does_not_fake_six(self):
        slow = measure(rows_for(folded(), [400] * 79, preempt=1200))["value"]
        fast = measure(rows_for(folded(), [100] * 79, preempt=1200))["value"]
        self.assertLess(slow, 4)
        self.assertGreater(fast, slow + 3)

    def test_hd_memory_requires_confusing_continuous_scene(self):
        confusing = rows_for(folded(), [90] * 79, preempt=1100)
        nm, hd = measure(confusing), measure(confusing, ["HD"])
        sparse = rows_for(line(step=100), [900] * 79, preempt=1200)
        sparse_nm, sparse_hd = measure(sparse), measure(sparse, ["HD"])
        self.assertGreater(hd["value"], nm["value"] + .5)
        self.assertGreater(hd["signals"]["remembered_conflict"], 0)
        self.assertLess(sparse_hd["value"], 3)
        self.assertLess(sparse_hd["value"] - sparse_nm["value"], .4)

    def test_high_ar_alone_cannot_emit_huge_reading(self):
        for preempt in (450, 300, 200):
            self.assertLess(measure(rows_for(line(step=100), [75] * 79,
                                             preempt=preempt))["value"], 4)

    def test_compact_fast_stream_does_not_borrow_wide_relocation_reading(self):
        wide_points = folded()
        compact_points = [(256 + (x - 256) * .28, 192 + (y - 192) * .28)
                          for x, y in wide_points]
        wide = measure(rows_for(wide_points, [60] * 79, preempt=450))
        compact = measure(rows_for(compact_points, [60] * 79, preempt=450))
        self.assertGreater(wide["signals"]["rapid_decode"],
                           compact["signals"]["rapid_decode"] + .5)

    def test_medium_speed_wide_aim_gets_only_small_reading_relief(self):
        medium = measure(rows_for(line(step=120), [125] * 79, preempt=500))
        extreme = measure(rows_for(folded(), [60] * 79, preempt=450))
        self.assertGreater(medium["signals"]["aim_read_relief"], .05)
        self.assertLessEqual(medium["signals"]["aim_read_relief"], .20)
        self.assertEqual(extreme["signals"]["aim_read_relief"], 0)

    def test_real_fold_and_low_ar_retention_protect_reading_from_aim_relief(self):
        folded_low_ar = measure(rows_for(folded(), [125] * 79, preempt=1100))
        self.assertGreater(folded_low_ar["signals"]["reading_protection"], .5)
        self.assertLess(folded_low_ar["signals"]["aim_read_relief"], .05)

    def test_short_hard_section_survives_easy_filler(self):
        hard = rows_for(folded(16), [75] * 15, preempt=1000)
        filler = rows_for(line(160, step=100), [900] * 159, preempt=1000)
        shift = hard[-1]["ls.start_time_ms"] + 4000
        for row in filler:
            row["ls.start_time_ms"] += shift
            row["ls.end_time_ms"] += shift
        self.assertAlmostEqual(measure(hard)["value"], measure(hard + filler)["value"])

    def test_separated_sections_cannot_combine_support(self):
        first = rows_for(folded(5), [75] * 4, preempt=1000)
        second = copy.deepcopy(first)
        shift = first[-1]["ls.start_time_ms"] + 4000
        for row in second:
            row["ls.start_time_ms"] += shift
            row["ls.end_time_ms"] += shift
        self.assertLessEqual(measure(first + second)["value"], measure(first)["value"] + 1e-9)

    def test_rigid_transforms_and_time_translation_are_invariant(self):
        points = folded()
        transformed = [(400 - y, 100 + x) for x, y in points]
        original_rows = rows_for(points, [95] * 79, preempt=900)
        moved_rows = rows_for(transformed, [95] * 79, preempt=900)
        for row in moved_rows:
            row["ls.start_time_ms"] += 5000
            row["ls.end_time_ms"] += 5000
        self.assertAlmostEqual(measure(original_rows)["value"], measure(moved_rows)["value"])

    def test_measure_has_no_star_or_other_axis_input(self):
        rows = rows_for(folded(), [90] * 79, preempt=900)
        altered = copy.deepcopy(rows)
        for row in altered:
            row.update({"stars": 18, "aim_control": 20, "raw_speed": 20})
        self.assertEqual(measure(rows), measure(altered))


class PublicBeta5ContractTests(unittest.TestCase):
    def setUp(self):
        self.rows = rows_for(folded(), [90] * 79, preempt=900)
        self.components, _ = candidate.extract_components(self.rows)
        self.kwargs = dict(checksum="sha256:" + "9" * 64,
                           components=self.components,
                           calibration=mini_calibration())

    def test_only_reading_changes_from_beta4(self):
        old = production.analyze_components(**self.kwargs)
        new = candidate.analyze_components(**self.kwargs)
        self.assertNotEqual(old["axes"]["reading"], new["axes"]["reading"])
        for axis in candidate.AXIS_ORDER:
            if axis != "reading":
                self.assertEqual(old["axes"][axis], new["axes"][axis], axis)

    def test_total_star_cannot_set_candidate_reading(self):
        values = []
        for stars in (1, 7, 15):
            self.components["v091_nm_star_anchor"] = stars
            values.append(candidate.analyze_components(**self.kwargs)["axes"]["reading"])
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[1], values[2])

    def test_candidate_requires_own_extraction_and_does_not_mutate_components(self):
        snapshot = copy.deepcopy(self.components)
        candidate.analyze_components(**self.kwargs)
        self.assertEqual(snapshot, self.components)
        self.components.pop("beta5_reading")
        with self.assertRaisesRegex(ValueError, "own local Reading extraction"):
            candidate.analyze_components(**self.kwargs)

    def test_beta5_is_registered_and_beta4_remains_available(self):
        from map_demand_v01 import release
        self.assertIs(release.runtime_model("v010-beta5"), candidate)
        self.assertIs(release.runtime_model("v010-beta4"), production)

    def test_public_identity_is_beta5(self):
        output = candidate.analyze_components(**self.kwargs)
        self.assertEqual(output["identity"]["map_demand_version"], "0.10.0-beta.5")
        self.assertEqual(output["release"]["stage"], "PUBLIC_BETA")
        self.assertEqual(output["axes"]["reading"]["method"],
                         "LOCAL_ORDER_MEMORY_READING_V1")


if __name__ == "__main__":
    unittest.main()

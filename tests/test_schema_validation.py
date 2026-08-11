import unittest

from osu_skill_profiler.models.baseline import DeterministicBaselineProfiler
from osu_skill_profiler.schema.annotation_schema import (
    ABSOLUTE_ANNOTATION_SCHEMA,
    ANNOTATOR_SCHEMA,
    PAIRWISE_ANNOTATION_SCHEMA,
    SEGMENT_ANNOTATION_SCHEMA,
)
from osu_skill_profiler.schema.output_schema import OUTPUT_SCHEMA
from osu_skill_profiler.schema.validate import validate

FIXTURE = __import__("pathlib").Path(__file__).parent / "fixtures" / "minimal.osu"


class OutputSchemaTests(unittest.TestCase):
    def test_baseline_output_is_valid(self):
        profile = DeterministicBaselineProfiler().analyze_map(str(FIXTURE))
        self.assertEqual(validate(profile, OUTPUT_SCHEMA), [])

    def test_missing_required_key_fails(self):
        profile = DeterministicBaselineProfiler().analyze_map(str(FIXTURE))
        del profile["skills"]
        self.assertNotEqual(validate(profile, OUTPUT_SCHEMA), [])

    def test_bad_skill_status_fails(self):
        profile = DeterministicBaselineProfiler().analyze_map(str(FIXTURE))
        profile["skills"]["jump_aim"]["status"] = "bogus"
        self.assertNotEqual(validate(profile, OUTPUT_SCHEMA), [])


class AnnotationSchemaTests(unittest.TestCase):
    def test_absolute_valid(self):
        record = {"annotation_id": "a1", "skill": "stream", "annotator_id": "ann-1", "value": "high"}
        self.assertEqual(validate(record, ABSOLUTE_ANNOTATION_SCHEMA), [])

    def test_absolute_invalid_value(self):
        record = {"annotation_id": "a1", "skill": "stream", "annotator_id": "ann-1", "value": "perfect"}
        self.assertNotEqual(validate(record, ABSOLUTE_ANNOTATION_SCHEMA), [])

    def test_pairwise_enum(self):
        record = {"annotation_id": "p1", "skill": "jump_aim", "annotator_id": "ann-1", "a_ref": "a.osu", "b_ref": "b.osu", "value": "a_higher"}
        self.assertEqual(validate(record, PAIRWISE_ANNOTATION_SCHEMA), [])
        record["value"] = "a_wins"
        self.assertNotEqual(validate(record, PAIRWISE_ANNOTATION_SCHEMA), [])

    def test_segment_annotation(self):
        record = {
            "annotation_id": "s1",
            "skill": "rhythm_complexity",
            "annotator_id": "ann-1",
            "segment_index": 2,
            "value": "low",
        }
        self.assertEqual(validate(record, SEGMENT_ANNOTATION_SCHEMA), [])

    def test_annotator_reliability_bounds(self):
        self.assertEqual(validate({"annotator_id": "ann-1", "reliability": 0.8}, ANNOTATOR_SCHEMA), [])
        self.assertNotEqual(validate({"annotator_id": "ann-1", "reliability": 1.5}, ANNOTATOR_SCHEMA), [])


if __name__ == "__main__":
    unittest.main()


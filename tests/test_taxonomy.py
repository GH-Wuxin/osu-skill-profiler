import unittest

from osu_skill_profiler.taxonomy import load_taxonomy, taxonomy_version


class TaxonomyTests(unittest.TestCase):
    def test_version_and_status(self):
        taxonomy = load_taxonomy()
        self.assertEqual(taxonomy["taxonomy_version"], "v0.0.1")
        self.assertEqual(taxonomy["status"], "PROVISIONAL")
        self.assertEqual(taxonomy_version(), "v0.0.1")

    def test_every_skill_has_required_fields(self):
        taxonomy = load_taxonomy()
        for skill in taxonomy["skills"]:
            for field in ("id", "provisional_definition", "not", "candidate_signals", "known_ambiguity"):
                self.assertIn(field, skill, f"{skill['id']} missing {field}")
            self.assertTrue(skill["candidate_signals"])

    def test_tech_is_not_atomic(self):
        taxonomy = load_taxonomy()
        ids = {skill["id"] for skill in taxonomy["skills"]}
        self.assertNotIn("tech", ids)
        labels = {label["id"]: label for label in taxonomy["convenience_labels"]}
        self.assertEqual(labels["tech"]["status"], "PROVISIONAL_CONVENIENCE_ONLY")
        self.assertTrue(labels["tech"]["derived_from"])

    def test_version_separation_is_explicit(self):
        taxonomy = load_taxonomy()
        self.assertIn("model_version_separation", taxonomy)


if __name__ == "__main__":
    unittest.main()


import unittest
from pathlib import Path

from osu_skill_profiler.dataset.manifest import ManifestError, load_manifest, validate_manifest
from osu_skill_profiler.dataset.split import split_by_beatmapset, split_by_mapper, validate_disjoint_split

FIXTURES = Path(__file__).parent / "fixtures"


def _sample(sample_id, beatmapset_id, mapper, difficulty):
    return {
        "sample_id": sample_id,
        "source": "local",
        "beatmap_id": 1000 + abs(hash(sample_id)) % 9000,
        "beatmapset_id": beatmapset_id,
        "mapper": mapper,
        "reference": f"fixtures/{sample_id}.osu",
        "checksum": "sha256:" + "0" * 64,
        "metadata": {"difficulty_name": difficulty},
    }


def _manifest(samples):
    return {
        "schema_version": "0.1.0",
        "parser_version": "0.1.0",
        "feature_version": "0.1.0",
        "samples": samples,
    }


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.samples = []
        for beatmapset_id, mapper in ((1001, "mapper-a"), (1002, "mapper-a"), (1003, "mapper-b")):
            for difficulty in ("Easy", "Insane"):
                self.samples.append(_sample(f"{beatmapset_id}-{difficulty}", beatmapset_id, mapper, difficulty))

    def test_beatmapset_disjoint(self):
        train, test = split_by_beatmapset(self.samples, train_ratio=0.67, seed=42)
        self.assertEqual(validate_disjoint_split(train, test), [])
        train_sets = {sample["beatmapset_id"] for sample in train}
        test_sets = {sample["beatmapset_id"] for sample in test}
        self.assertTrue(train_sets.isdisjoint(test_sets))
        self.assertGreater(len(train), 0)
        self.assertGreater(len(test), 0)

    def test_split_is_seed_deterministic(self):
        first = split_by_beatmapset(self.samples, train_ratio=0.67, seed=7)
        second = split_by_beatmapset(self.samples, train_ratio=0.67, seed=7)
        self.assertEqual([s["sample_id"] for s in first[0]], [s["sample_id"] for s in second[0]])
        self.assertEqual([s["sample_id"] for s in first[1]], [s["sample_id"] for s in second[1]])

    def test_mapper_disjoint(self):
        train, test = split_by_mapper(self.samples, train_ratio=0.6, seed=42)
        self.assertEqual(validate_disjoint_split(train, test, key="mapper"), [])

    def test_ungrouped_samples_never_leak(self):
        samples = [
            {"sample_id": "a", "source": "local", "mapper": "m", "reference": "a.osu", "checksum": "sha256:" + "0" * 64},
            {"sample_id": "b", "source": "local", "mapper": "m", "reference": "b.osu", "checksum": "sha256:" + "0" * 64},
            {"sample_id": "c", "source": "local", "mapper": "m", "reference": "c.osu", "checksum": "sha256:" + "0" * 64},
        ]
        train, test = split_by_beatmapset(samples, train_ratio=0.67, seed=1)
        self.assertEqual(validate_disjoint_split(train, test), [])


class ManifestTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        validate_manifest(_manifest([_sample("s1", 1001, "m", "Normal")]))

    def test_duplicate_sample_id_rejected(self):
        manifest = _manifest([_sample("s1", 1001, "m", "Normal"), _sample("s1", 1001, "m", "Hard")])
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_bad_checksum_rejected(self):
        sample = _sample("s1", 1001, "m", "Normal")
        sample["checksum"] = "md5:abc"
        with self.assertRaises(ManifestError):
            validate_manifest(_manifest([sample]))

    def test_fixture_manifest_loads(self):
        manifest = load_manifest(FIXTURES / "manifest.json")
        self.assertGreater(len(manifest["samples"]), 0)


if __name__ == "__main__":
    unittest.main()


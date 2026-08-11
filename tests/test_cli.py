import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from osu_skill_profiler.cli.main import main
from osu_skill_profiler.dataset.manifest import checksum_file

FIXTURES = Path(__file__).parent / "fixtures"


class CliTests(unittest.TestCase):
    def _quiet(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_profile_map_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "profile.json"
            code, _ = self._quiet(["profile-map", str(FIXTURES / "minimal.osu"), "--out", str(out)])
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "0.1.0")
            self.assertEqual(payload["status"], "not_inferred")

    def test_extract_features(self):
        code, output = self._quiet(["extract-features", str(FIXTURES / "minimal.osu")])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertIn("temporal.object_count", payload["features"])

    def test_inspect_segments(self):
        code, output = self._quiet(["inspect-segments", str(FIXTURES / "sliders.osu"), "--window-ms", "5000"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertGreater(len(payload["segments"]), 0)
        self.assertIn("aggregated_features", payload)

    def test_validate_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "schema_version": "0.1.0",
                "parser_version": "0.1.0",
                "feature_version": "0.1.0",
                "samples": [
                    {
                        "sample_id": "minimal",
                        "source": "local",
                        "beatmap_id": 1000001,
                        "beatmapset_id": 2000001,
                        "mapper": "fixture-mapper",
                        "reference": str(FIXTURES / "minimal.osu"),
                        "checksum": checksum_file(FIXTURES / "minimal.osu"),
                        "metadata": {"difficulty_name": "Normal"},
                    }
                ],
            }
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            code, output = self._quiet(["validate-dataset", str(path), "--verify-checksums"])
            self.assertEqual(code, 0)
            self.assertIn('"valid": true', output)

    def test_validate_dataset_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "schema_version": "0.1.0",
                "parser_version": "0.1.0",
                "feature_version": "0.1.0",
                "samples": [
                    {
                        "sample_id": "ghost",
                        "source": "local",
                        "mapper": "m",
                        "reference": "does-not-exist.osu",
                        "checksum": "sha256:" + "0" * 64,
                    }
                ],
            }
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            code, output = self._quiet(["validate-dataset", str(path), "--verify-checksums"])
            self.assertEqual(code, 1)
            self.assertIn('"valid": false', output)

    def test_validate_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            self._quiet(["profile-map", str(FIXTURES / "minimal.osu"), "--out", str(profile_path)])
            code, _ = self._quiet(["validate-profile", str(profile_path)])
            self.assertEqual(code, 0)

    def test_deterministic_cli_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.json"
            second = Path(tmp) / "b.json"
            self._quiet(["profile-map", str(FIXTURES / "unusual_sv.osu"), "--out", str(first)])
            self._quiet(["profile-map", str(FIXTURES / "unusual_sv.osu"), "--out", str(second)])
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_file_returns_error(self):
        code, _ = self._quiet(["profile-map", str(FIXTURES / "nope.osu")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


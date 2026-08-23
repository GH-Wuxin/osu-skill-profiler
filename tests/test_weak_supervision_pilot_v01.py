from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/weak_supervision_pilot_v01.py"
SPEC = importlib.util.spec_from_file_location("weak_supervision_pilot_v01", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PilotSelectionTests(unittest.TestCase):
    def _rows(self):
        return {
            "sha256:" + f"{index:064x}": {
                "checksum": "sha256:" + f"{index:064x}",
                "sample_id": f"map-{index}",
                "features": {},
            }
            for index in range(1, 31)
        }

    def test_selection_is_deterministic_and_bounded(self):
        rows = self._rows()
        keys = sorted(rows)
        challenges = {
            "legacy_format_ood": set(keys[:4]),
            "pathological_challenge": set(keys[4:8]),
            "reference_disagreement_challenge": set(keys[8:10]),
        }
        first = MODULE.select_pilot(rows, challenges, 20, "seed")
        second = MODULE.select_pilot(dict(reversed(list(rows.items()))), challenges, 20, "seed")
        self.assertEqual([row["checksum"] for row in first], [row["checksum"] for row in second])
        self.assertEqual(len(first), 20)

    def test_selection_rejects_unbounded_size(self):
        with self.assertRaises(ValueError):
            MODULE.select_pilot(self._rows(), {name: set() for name in ("legacy_format_ood", "pathological_challenge", "reference_disagreement_challenge")}, 5001, "seed")

    def test_selected_jsonl_skips_giant_unselected_rows(self):
        checksum = "sha256:" + "1" * 64
        other = "sha256:" + "2" * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_text(
                json.dumps({"checksum": other, "payload": "x" * 1000}) + "\n" +
                json.dumps({"checksum": checksum, "payload": 1}) + "\n",
                encoding="utf-8",
            )
            rows = list(MODULE.iter_selected_jsonl(path, {checksum}))
            self.assertEqual(rows, [{"checksum": checksum, "payload": 1}])

    def test_normalized_output_rejects_absolute_paths_and_nonfinite(self):
        MODULE.assert_normalized_output({"relative": "training/data.jsonl"})
        with self.assertRaises(ValueError):
            MODULE.assert_normalized_output({"bad": "C:/private/data"})
        with self.assertRaises(ValueError):
            MODULE.assert_normalized_output({"bad": float("inf")})


if __name__ == "__main__":
    unittest.main()

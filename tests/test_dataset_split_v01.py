"""Synthetic leakage/grouping tests for the v0.1 split boundary."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from osu_skill_profiler.dataset.split_v01 import (
    DEFAULT_SEED,
    SPLIT_VERSION,
    assign_benchmark,
    group_hash,
    legacy_format_flags,
    mapper_group_key,
    pathological_reasons,
    set_group_key,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "dataset_split_audit.py"


def _checksum(tag: str) -> str:
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def _record(
    sample_id: str,
    *,
    beatmapset_id: int | None = None,
    local_set_group: str | None = None,
    mapper: str | None = "mapper-a",
    format_version: int = 14,
    metadata: dict | None = None,
) -> dict:
    record = {
        "map_checksum": _checksum(sample_id),
        "sample_id": sample_id,
        "beatmap_id": None,
        "beatmapset_id": beatmapset_id,
        "local_set_group": local_set_group,
        "mapper": mapper,
        "creator": mapper,
        "format_version": format_version,
        "metadata": metadata or {},
    }
    set_key, set_policy = set_group_key(record)
    mapper_key, mapper_quality = mapper_group_key(record)
    record["set_group_key"] = set_key
    record["set_group_policy"] = set_policy
    record["mapper_group_key"] = mapper_key
    record["mapper_identity_quality"] = mapper_quality
    record["duplicate_class"] = "UNIQUE"
    record["subset_flags"] = legacy_format_flags(format_version)
    record["pathological_reasons"] = pathological_reasons(record)
    return record


def _split_of(rows, checksum):
    for row in rows:
        if row["map_checksum"] == checksum:
            return row["split"]
    return None


class SetDisjointTests(unittest.TestCase):
    def test_two_difficulties_in_one_beatmapset_never_cross(self):
        records = [
            _record("s1-easy", beatmapset_id=1001, local_set_group="set-1001"),
            _record("s1-insane", beatmapset_id=1001, local_set_group="set-1001"),
            _record("s2-easy", beatmapset_id=1002, local_set_group="set-1002"),
            _record("s2-insane", beatmapset_id=1002, local_set_group="set-1002"),
        ]
        rows = assign_benchmark(records, ["set_group_key"], benchmark="set_disjoint")
        by_set: dict[str, set[str]] = {}
        for row in rows:
            by_set.setdefault(row["set_group_key"], set()).add(row["split"])
        for splits in by_set.values():
            self.assertEqual(len(splits), 1)
        self.assertEqual(len(rows), 4)

    def test_absent_beatmapset_id_falls_back_to_local_set_group(self):
        records = [
            _record("s1-easy", local_set_group="folder-a"),
            _record("s1-insane", local_set_group="folder-a"),
            _record("s2-easy", local_set_group="folder-b"),
            _record("s2-insane", local_set_group="folder-b"),
        ]
        rows = assign_benchmark(records, ["set_group_key"], benchmark="set_disjoint")
        by_set: dict[str, set[str]] = {}
        for row in rows:
            by_set.setdefault(row["set_group_key"], set()).add(row["split"])
        for splits in by_set.values():
            self.assertEqual(len(splits), 1)

    def test_same_artist_title_different_mapper_not_merged(self):
        records = [
            _record(
                "a1",
                beatmapset_id=2001,
                mapper="mapper-x",
                metadata={
                    "artist": "Artist",
                    "title": "Title",
                    "duration_ms": 100000,
                    "counts": {"objects": 100, "sliders": 50, "timing_points": 1},
                },
            ),
            _record(
                "a2",
                beatmapset_id=2002,
                mapper="mapper-y",
                metadata={
                    "artist": "Artist",
                    "title": "Title",
                    "duration_ms": 100000,
                    "counts": {"objects": 100, "sliders": 50, "timing_points": 1},
                },
            ),
        ]
        from osu_skill_profiler.dataset.split_v01 import build_components

        _, components = build_components(records, ["set_group_key"])
        # Same artist/title must never become a hard grouping constraint:
        # the two maps stay in separate set components.
        self.assertEqual(len(components), 2)
        rows = assign_benchmark(records, ["set_group_key"], benchmark="set_disjoint")
        self.assertEqual({r["set_group_key"] for r in rows}, {"b:2001", "b:2002"})


class MapperDisjointTests(unittest.TestCase):
    def test_same_mapper_across_sets_never_crosses(self):
        records = [
            _record("s1", beatmapset_id=3001, mapper="shared-mapper"),
            _record("s2", beatmapset_id=3002, mapper="shared-mapper"),
            _record("s3", beatmapset_id=3003, mapper="other-mapper"),
            _record("s4", beatmapset_id=3004, mapper="other-mapper"),
        ]
        rows = assign_benchmark(
            records,
            ["mapper_group_key"],
            include_unknown_mapper=False,
            benchmark="mapper_disjoint",
        )
        by_mapper: dict[str, set[str]] = {}
        for row in rows:
            by_mapper.setdefault(row["mapper_group_key"], set()).add(row["split"])
        for splits in by_mapper.values():
            self.assertEqual(len(splits), 1)

    def test_unknown_mapper_excluded(self):
        records = [
            _record("s1", beatmapset_id=4001, mapper=None),
            _record("s2", beatmapset_id=4002, mapper="known"),
        ]
        known = [r for r in records if r["mapper_identity_quality"] == "NAME_ONLY"]
        unknown = [r for r in records if r["mapper_identity_quality"] == "UNKNOWN"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(len(known), 1)
        rows = assign_benchmark(
            known,
            ["mapper_group_key"],
            include_unknown_mapper=False,
            benchmark="mapper_disjoint",
        )
        self.assertEqual([r["map_checksum"] for r in rows], [records[1]["map_checksum"]])


class DuplicateTests(unittest.TestCase):
    def test_duplicate_checksum_never_crosses(self):
        checksum = _checksum("same-content")
        first = _record("copy-a", beatmapset_id=5001, local_set_group="folder-a")
        second = _record("copy-b", beatmapset_id=5001, local_set_group="folder-a")
        first["map_checksum"] = checksum
        second["map_checksum"] = checksum
        rows = assign_benchmark([first, second], ["set_group_key"], benchmark="set_disjoint")
        self.assertEqual(_split_of(rows, checksum), _split_of(rows, checksum))
        self.assertEqual(len({r["split"] for r in rows}), 1)


class ChallengeFlagTests(unittest.TestCase):
    def test_legacy_format_flag(self):
        self.assertIn("legacy_format", legacy_format_flags(3))
        self.assertIn("legacy_format", legacy_format_flags(5))
        self.assertNotIn("legacy_format", legacy_format_flags(6))
        self.assertNotIn("legacy_format", legacy_format_flags(14))
        self.assertIn("format_v128", legacy_format_flags(128))

    def test_pathological_reasons_from_flags_and_metadata(self):
        record = _record(
            "path-map",
            beatmapset_id=6001,
            metadata={
                "bpm_max": 1e300,
                "repeats_max": 2000,
                "counts": {"objects": 10, "sliders": 10, "timing_points": 1},
                "difficulty": {},
            },
        )
        reasons = pathological_reasons(record, qa_flags=["aspire_like"])
        self.assertIn("qa_flag:aspire_like", reasons)
        self.assertIn("bpm_extreme_finite", reasons)
        self.assertIn("repeats_extreme_finite", reasons)
        self.assertIn("all_slider", reasons)

    def test_ordinary_map_has_no_pathological_reasons(self):
        record = _record(
            "normal-map",
            beatmapset_id=6002,
            metadata={
                "bpm_max": 180.0,
                "repeats_max": 2,
                "counts": {"objects": 200, "sliders": 80, "timing_points": 1},
                "difficulty": {},
            },
        )
        self.assertEqual(pathological_reasons(record, qa_flags=[]), [])


class StrictDisjointTests(unittest.TestCase):
    def test_strict_set_and_mapper_connected_grouping(self):
        records = [
            _record("s1-easy", beatmapset_id=7001, mapper="shared"),
            _record("s1-insane", beatmapset_id=7001, mapper="shared"),
            _record("s2-hard", beatmapset_id=7002, mapper="shared"),
            _record("s3", beatmapset_id=7003, mapper="other"),
            _record("s4", beatmapset_id=7004, mapper="other"),
        ]
        rows = assign_benchmark(
            records, ["set_group_key", "mapper_group_key"], benchmark="strict_disjoint"
        )
        connected = {records[i]["map_checksum"] for i in range(3)}
        splits = {r["map_checksum"]: r["split"] for r in rows}
        self.assertEqual(len({splits[c] for c in connected}), 1)
        by_mapper: dict[str, set[str]] = {}
        by_set: dict[str, set[str]] = {}
        for row in rows:
            by_mapper.setdefault(row["mapper_group_key"], set()).add(row["split"])
            by_set.setdefault(row["set_group_key"], set()).add(row["split"])
        for splits_set in list(by_mapper.values()) + list(by_set.values()):
            self.assertEqual(len(splits_set), 1)


class DeterminismTests(unittest.TestCase):
    def test_group_hash_is_content_based_and_seed_sensitive(self):
        first = group_hash(SPLIT_VERSION, DEFAULT_SEED, "b:1")
        second = group_hash(SPLIT_VERSION, DEFAULT_SEED, "b:1")
        self.assertEqual(first, second)
        different_key = group_hash(SPLIT_VERSION, DEFAULT_SEED, "b:2")
        different_seed = group_hash(SPLIT_VERSION, "other-seed", "b:1")
        self.assertNotEqual(first, different_key)
        self.assertNotEqual(first, different_seed)

    def test_repeated_generation_identical(self):
        records = [
            _record(f"s{i}", beatmapset_id=8000 + i % 5, local_set_group=f"g{i % 5}")
            for i in range(30)
        ]
        first = assign_benchmark(records, ["set_group_key"], benchmark="set_disjoint")
        second = assign_benchmark(records, ["set_group_key"], benchmark="set_disjoint")
        self.assertEqual(first, second)

    def test_input_order_does_not_change_membership(self):
        records = [
            _record(f"s{i}", beatmapset_id=9000 + i % 7, local_set_group=f"g{i % 7}")
            for i in range(50)
        ]
        baseline = assign_benchmark(records, ["set_group_key"], benchmark="set_disjoint")
        shuffled = assign_benchmark(
            list(reversed(records)), ["set_group_key"], benchmark="set_disjoint"
        )
        self.assertEqual(baseline, shuffled)


class IntegrationRegenerationTests(unittest.TestCase):
    def _write_manifest(self, path: Path, records: list[dict]) -> None:
        samples = []
        for i, record in enumerate(records):
            samples.append(
                {
                    "sample_id": record["sample_id"],
                    "source": "local_osu_songs",
                    "reference": f"{record['sample_id']}.osu",
                    "relative_path": f"{record['sample_id']}.osu",
                    "checksum": record["map_checksum"],
                    "sha256": record["map_checksum"],
                    "beatmap_id": record.get("beatmap_id"),
                    "beatmapset_id": record.get("beatmapset_id"),
                    "beatmapset_id_source": "metadata",
                    "local_set_group": record.get("local_set_group"),
                    "artist": "Artist",
                    "title": "Title",
                    "creator": record.get("mapper"),
                    "mapper": record.get("mapper"),
                    "version": f"v{i}",
                    "mode": 0,
                    "format_version": record.get("format_version"),
                    "parser_version": "0.1.0",
                    "feature_version": "0.1.0",
                    "metadata": record.get("metadata"),
                }
            )
        manifest = {
            "schema_version": "0.1.0",
            "parser_version": "0.1.0",
            "feature_version": "0.1.0",
            "samples": samples,
        }
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                '{"schema_version": "0.1.0", "parser_version": "0.1.0", '
                '"feature_version": "0.1.0", "samples": [\n'
            )
            for index, sample in enumerate(samples):
                comma = "," if index < len(samples) - 1 else ""
                handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + comma + "\n")
            handle.write("]}\n")

    def test_repeated_generation_is_byte_identical(self):
        records = [
            _record(f"t{i}", beatmapset_id=10000 + i % 6, local_set_group=f"tg{i % 6}")
            for i in range(24)
        ]
        with tempfile.TemporaryDirectory(prefix="split-int-") as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            self._write_manifest(manifest, records)
            feature_qa = root / "feature_qa.jsonl"
            ref_qa = root / "ref_qa.jsonl"
            with feature_qa.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(
                        json.dumps(
                            {
                                "checksum": record["map_checksum"],
                                "flags": [],
                                "short_lt100": False,
                                "short_lt1000": False,
                                "ok": True,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
            ref_qa.write_bytes(feature_qa.read_bytes())
            empty = root / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            outputs = []
            for run in range(2):
                out = root / f"out-{run}"
                cmd = [
                    sys.executable,
                    str(TOOL),
                    "generate",
                    "--manifest",
                    str(manifest),
                    "--feature-qa",
                    str(feature_qa),
                    "--ref-qa",
                    str(ref_qa),
                    "--disagreement",
                    str(empty),
                    "--out",
                    str(out),
                    "--seed",
                    DEFAULT_SEED,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                digests = {}
                for path in sorted(out.iterdir()):
                    if path.is_file() and path.name not in (
                        "summary.json",
                        "manifest.json",
                    ):
                        digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                outputs.append(digests)
            self.assertEqual(outputs[0], outputs[1])

    def test_version_metadata_overrides_are_recorded(self):
        records = [
            _record(f"v{i}", beatmapset_id=20000 + i % 6, local_set_group=f"vg{i % 6}")
            for i in range(12)
        ]
        with tempfile.TemporaryDirectory(prefix="split-ver-") as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            self._write_manifest(manifest, records)
            feature_qa = root / "feature_qa.jsonl"
            ref_qa = root / "ref_qa.jsonl"
            with feature_qa.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(
                        json.dumps(
                            {
                                "checksum": record["map_checksum"],
                                "flags": [],
                                "short_lt100": False,
                                "short_lt1000": False,
                                "ok": True,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
            ref_qa.write_bytes(feature_qa.read_bytes())
            empty = root / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            out = root / "out"
            cmd = [
                sys.executable,
                str(TOOL),
                "generate",
                "--manifest",
                str(manifest),
                "--feature-qa",
                str(feature_qa),
                "--ref-qa",
                str(ref_qa),
                "--disagreement",
                str(empty),
                "--out",
                str(out),
                "--seed",
                DEFAULT_SEED,
                "--feature-version",
                "0.2.0",
                "--local-version",
                "0.3.0",
                "--reference-version",
                "0.2.0",
                "--challenge-version",
                "0.2.0",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["feature_version"], "0.2.0")
            self.assertEqual(summary["local_signal_version"], "0.3.0")
            self.assertEqual(summary["reference_signal_version"], "0.2.0")
            self.assertEqual(
                summary["challenge_subset_versions"],
                {
                    "legacy_format_ood": "0.2.0",
                    "pathological_challenge": "0.2.0",
                    "reference_disagreement_challenge": "0.2.0",
                },
            )
            dataset_manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(dataset_manifest["feature_version"], "0.2.0")
            self.assertEqual(dataset_manifest["local_signal_version"], "0.3.0")
            self.assertEqual(dataset_manifest["reference_signal_version"], "0.2.0")


if __name__ == "__main__":
    unittest.main()

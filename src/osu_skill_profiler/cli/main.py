"""Minimal CLI.

Commands:
  profile-map MAP.OSU          -> versioned skill-profile JSON
  extract-features MAP.OSU     -> full-map deterministic features
  inspect-segments MAP.OSU     -> segment representation
  validate-dataset MANIFEST    -> manifest validation report
  validate-profile PROFILE     -> output schema validation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import SCHEMA_VERSION
from ..dataset.manifest import load_manifest, verify_manifest_files
from ..features.extractor import FeatureExtractor
from ..models.baseline import DeterministicBaselineProfiler
from ..parser.normalized import normalize
from ..parser.osu_parser import parse_osu_file
from ..schema.annotation_schema import ANNOTATION_SCHEMAS
from ..schema.output_schema import OUTPUT_SCHEMA
from ..schema.validate import ValidationError, validate
from ..segments.aggregator import aggregate_features
from ..taxonomy import taxonomy_version


def _emit(payload: dict, out: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"written: {out}")
    else:
        sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="osu-skill-profiler", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("profile-map", help="produce a versioned skill-profile JSON")
    profile.add_argument("map", type=Path)
    profile.add_argument("--out", type=Path)
    profile.add_argument("--segment-strategy", choices=["fixed_time", "fixed_count"], default="fixed_time")
    profile.add_argument("--window-ms", type=float, default=5000.0)
    profile.add_argument("--chunk-size", type=int, default=20)
    profile.add_argument("--no-weak-labels", action="store_true")

    features = subparsers.add_parser("extract-features", help="full-map deterministic features")
    features.add_argument("map", type=Path)
    features.add_argument("--out", type=Path)

    local_signals = subparsers.add_parser(
        "extract-local-signals",
        help="per-object corrected Local Signal Layer document (observable signals only)",
    )
    local_signals.add_argument("map", type=Path)
    local_signals.add_argument("--out", type=Path)
    local_signals.add_argument("--window-ms", type=float, default=5000.0)

    reference_signals = subparsers.add_parser(
        "extract-reference-signals",
        help="per-object corrected Official Reference Signal document (REFERENCE_ONLY, never ground truth)",
    )
    reference_signals.add_argument("map", type=Path)
    reference_signals.add_argument("--out", type=Path)
    reference_signals.add_argument("--window-ms", type=float, default=5000.0)

    segments = subparsers.add_parser("inspect-segments", help="segment representation")
    segments.add_argument("map", type=Path)
    segments.add_argument("--segment-strategy", choices=["fixed_time", "fixed_count"], default="fixed_time")
    segments.add_argument("--window-ms", type=float, default=5000.0)
    segments.add_argument("--chunk-size", type=int, default=20)
    segments.add_argument("--out", type=Path)

    dataset = subparsers.add_parser("validate-dataset", help="validate a dataset manifest")
    dataset.add_argument("manifest", type=Path)
    dataset.add_argument("--verify-checksums", action="store_true")
    dataset.add_argument("--base-dir", type=Path)

    profile_check = subparsers.add_parser("validate-profile", help="validate a profile JSON against the public schema")
    profile_check.add_argument("profile", type=Path)

    subparsers.add_parser("taxonomy", help="print the provisional taxonomy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "profile-map":
            profiler = DeterministicBaselineProfiler(
                segment_strategy=args.segment_strategy,
                window_ms=args.window_ms,
                chunk_size=args.chunk_size,
                run_weak_labels=not args.no_weak_labels,
            )
            output = profiler.analyze_map(str(args.map), source_label=str(args.map))
            _emit(output, str(args.out) if args.out else None)
        elif args.command == "extract-features":
            nmap = normalize(parse_osu_file(args.map))
            features = FeatureExtractor().extract(nmap)
            _emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "feature_version": FeatureExtractor.feature_version,
                    "source": str(args.map),
                    "features": features,
                },
                str(args.out) if args.out else None,
            )
        elif args.command == "extract-local-signals":
            from ..signals.extractor import LocalSignalExtractor, segment_local_signals

            beatmap = parse_osu_file(args.map)
            extractor = LocalSignalExtractor()
            output = extractor.extract(beatmap)
            output["segments"] = segment_local_signals(output["objects"], window_ms=args.window_ms)
            output["source"] = str(args.map)
            _emit(output, str(args.out) if args.out else None)
        elif args.command == "extract-reference-signals":
            from ..reference.ppy.extractor import ReferenceSignalExtractor, segment_reference_signals

            beatmap = parse_osu_file(args.map)
            extractor = ReferenceSignalExtractor()
            output = extractor.extract(beatmap)
            output["segments"] = segment_reference_signals(output["objects"], window_ms=args.window_ms)
            output["source"] = str(args.map)
            _emit(output, str(args.out) if args.out else None)
        elif args.command == "inspect-segments":
            profiler = DeterministicBaselineProfiler(
                segment_strategy=args.segment_strategy,
                window_ms=args.window_ms,
                chunk_size=args.chunk_size,
                run_weak_labels=False,
            )
            from ..segments.base import Segment

            segments = profiler.analyze_segments(str(args.map))
            segment_objects = [
                Segment(segment["start_ms"], segment["end_ms"], segment["start_idx"], segment["end_idx"], segment["features"])
                for segment in segments
            ]
            output = {
                "schema_version": SCHEMA_VERSION,
                "taxonomy_version": taxonomy_version(),
                "source": str(args.map),
                "segments": segments,
                "aggregated_features": aggregate_features(segment_objects),
            }
            _emit(output, str(args.out) if args.out else None)
        elif args.command == "validate-dataset":
            manifest = load_manifest(args.manifest)
            errors = verify_manifest_files(manifest, args.base_dir) if args.verify_checksums else []
            report = {
                "schema_version": SCHEMA_VERSION,
                "manifest": str(args.manifest),
                "sample_count": len(manifest["samples"]),
                "valid": not errors,
                "errors": errors,
            }
            _emit(report, None)
            return 0 if not errors else 1
        elif args.command == "validate-profile":
            profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
            errors = validate(profile, OUTPUT_SCHEMA)
            report = {"valid": not errors, "errors": errors}
            _emit(report, None)
            return 0 if not errors else 1
        elif args.command == "taxonomy":
            from ..taxonomy import load_taxonomy

            _emit(load_taxonomy(), None)
        return 0
    except (ValueError, ValidationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

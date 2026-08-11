"""Deterministic baseline profiler.

This is a pipeline smoke test, not a skill model. It runs parse -> normalize
-> segment -> aggregate -> weak labels and always reports every skill as
``not_inferred``. No score is ever fabricated.
"""

from __future__ import annotations

from pathlib import Path

from .. import SCHEMA_VERSION
from ..features.extractor import FeatureExtractor
from ..parser.model import Beatmap
from ..parser.normalized import NormalizedBeatmap, normalize
from ..parser.osu_parser import parse_osu_file
from ..schema.output_schema import OUTPUT_SCHEMA
from ..schema.validate import assert_valid
from ..segments.aggregator import aggregate_features
from ..segments.fixed_count import FixedObjectCountStrategy
from ..segments.fixed_time import FixedTimeWindowStrategy
from ..taxonomy import load_taxonomy, taxonomy_version
from ..weak_supervision.engine import apply_weak_rules, checksum_normalized
from ..weak_supervision.rules import CONSERVATIVE_RULES

DISCLAIMER = "BASELINE / NOT TRAINED / NOT GROUND TRUTH"


class DeterministicBaselineProfiler:
    model_kind = "baseline"
    model_version = "deterministic-baseline-0.1.0"

    def __init__(
        self,
        segment_strategy: str = "fixed_time",
        window_ms: float = 5000.0,
        chunk_size: int = 20,
        run_weak_labels: bool = True,
    ) -> None:
        self.taxonomy_version = taxonomy_version()
        self.run_weak_labels = run_weak_labels
        self.extractor = FeatureExtractor()
        if segment_strategy == "fixed_time":
            self.strategy = FixedTimeWindowStrategy(window_ms=window_ms)
        elif segment_strategy == "fixed_count":
            self.strategy = FixedObjectCountStrategy(chunk_size=chunk_size)
        else:
            raise ValueError("segment_strategy must be 'fixed_time' or 'fixed_count'")

    def _load(self, source: str | NormalizedBeatmap | Beatmap) -> NormalizedBeatmap:
        if isinstance(source, NormalizedBeatmap):
            return source
        if isinstance(source, Beatmap):
            return normalize(source)
        return normalize(parse_osu_file(source))

    def analyze_segments(self, source: str | NormalizedBeatmap | Beatmap) -> list[dict]:
        nmap = self._load(source)
        segments = self.strategy.segment(nmap, self.extractor)
        return [
            {
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "start_idx": segment.start_idx,
                "end_idx": segment.end_idx,
                "features": segment.features,
            }
            for segment in segments
        ]

    def analyze_map(self, source: str | NormalizedBeatmap | Beatmap, source_label: str | None = None) -> dict:
        nmap = self._load(source)
        segments = self.strategy.segment(nmap, self.extractor)
        features = aggregate_features(segments)
        weak_labels = []
        if self.run_weak_labels:
            # Weak rules consume full-map deterministic features; the public
            # ``features`` field stays segment-aggregated per the architecture.
            weak_features = self.extractor.extract(nmap)
            weak_labels = [
                record.as_dict()
                for record in apply_weak_rules(
                    weak_features,
                    segments,
                    CONSERVATIVE_RULES,
                    checksum_normalized(nmap),
                )
            ]
        beatmap = nmap.beatmap
        difficulty = beatmap.difficulty
        output = {
            "schema_version": SCHEMA_VERSION,
            "taxonomy_version": self.taxonomy_version,
            "model_version": self.model_version,
            "model_kind": self.model_kind,
            "status": "not_inferred",
            "disclaimer": DISCLAIMER,
            "beatmap": {
                "beatmap_id": beatmap.metadata.get("BeatmapID"),
                "beatmapset_id": beatmap.metadata.get("BeatmapSetID"),
                "mapper": beatmap.metadata.get("Creator", ""),
                "difficulty_name": beatmap.metadata.get("Version", ""),
                "source": source_label or ("<inline>" if not isinstance(source, (str, Path)) else str(source)),
                "difficulty": {
                    "AR": difficulty.get("ApproachRate"),
                    "OD": difficulty.get("OverallDifficulty"),
                    "CS": difficulty.get("CircleSize"),
                    "HP": difficulty.get("HPDrainRate"),
                    "SliderMultiplier": difficulty.get("SliderMultiplier"),
                    "SliderTickRate": difficulty.get("SliderTickRate"),
                },
            },
            "features": features,
            "skills": {
                skill["id"]: {"score": None, "confidence": None, "status": "not_inferred"}
                for skill in load_taxonomy()["skills"]
            },
            "segments": self.analyze_segments(nmap),
            "weak_labels": weak_labels,
        }
        assert_valid(output, OUTPUT_SCHEMA, "profile")
        return output

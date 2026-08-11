"""Weak-label engine: applies conservative rules and attaches provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from ..features.extractor import FeatureExtractor
from ..parser.normalized import NormalizedBeatmap
from ..segments.base import Segment
from ..taxonomy import taxonomy_version
from .base import WEAK_LABEL_DISCLAIMER, WeakLabelEvidence, WeakLabelResult, WeakLabelRule


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def checksum_normalized(nmap: NormalizedBeatmap) -> str:
    """Stable input checksum so weak-label provenance can be audited."""

    objects = [
        {
            "time_ms": obj.time_ms,
            "x_norm": obj.x_norm,
            "y_norm": obj.y_norm,
            "type": obj.raw.object_type,
            "slider_slides": obj.raw.slider_slides,
            "slider_pixel_length": obj.raw.slider_pixel_length,
        }
        for obj in nmap.objects
    ]
    timing = [
        {
            "time_ms": point.time_ms,
            "beat_length_ms": point.beat_length_ms,
            "uninherited": point.uninherited,
        }
        for point in nmap.beatmap.timing_points
    ]
    body = canonical_json({"objects": objects, "timing": timing})
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def apply_weak_rules(
    features: dict,
    segments: list[Segment],
    rules: Iterable[WeakLabelRule],
    input_checksum: str,
    feature_version: str = FeatureExtractor.feature_version,
) -> list[WeakLabelEvidence]:
    """Apply every rule and wrap results in provenance-carrying evidence."""

    tax_version = taxonomy_version()
    evidence_list: list[WeakLabelEvidence] = []
    for rule in rules:
        for result in rule.apply(features, segments):
            evidence_list.append(
                WeakLabelEvidence(
                    rule_id=result.rule_id,
                    skill=result.skill,
                    suggested_score=result.suggested_score,
                    confidence=result.confidence,
                    evidence=result.evidence,
                    segment_index=result.segment_index,
                    features_version=feature_version,
                    taxonomy_version=tax_version,
                    input_checksum=input_checksum,
                    disclaimer=WEAK_LABEL_DISCLAIMER,
                )
            )
    evidence_list.sort(key=lambda item: (item.rule_id, item.skill))
    return evidence_list


def run_weak_rules(
    nmap: NormalizedBeatmap,
    segments: list[Segment],
    rules: Iterable[WeakLabelRule] | None = None,
    extractor: FeatureExtractor | None = None,
) -> list[WeakLabelEvidence]:
    """Convenience wrapper: extract map-level features and run the rules."""

    if extractor is None:
        extractor = FeatureExtractor()
    features = extractor.extract(nmap)
    checksum = checksum_normalized(nmap)
    return apply_weak_rules(features, segments, rules or [], checksum)


def save_weak_labels(records: list[WeakLabelEvidence] | list[WeakLabelResult], path: str | Path) -> None:
    """Persist weak labels as versioned JSON with provenance (never as truth)."""

    payload = {
        "kind": "weak_labels",
        "note": WEAK_LABEL_DISCLAIMER,
        "records": [
            record.as_dict() if isinstance(record, WeakLabelEvidence) else {
                "rule_id": record.rule_id,
                "skill": record.skill,
                "suggested_score": record.suggested_score,
                "confidence": record.confidence,
                "evidence": list(record.evidence),
                "segment_index": record.segment_index,
            }
            for record in records
        ],
    }
    Path(path).write_text(canonical_json(payload) + "\n", encoding="utf-8")


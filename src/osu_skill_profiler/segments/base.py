"""Segment abstraction shared by all segmentation strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..features.extractor import FeatureExtractor
from ..parser.normalized import NormalizedBeatmap


@dataclass(frozen=True)
class Segment:
    start_ms: float
    end_ms: float
    start_idx: int
    end_idx: int  # exclusive
    features: dict


class SegmentStrategy(Protocol):
    name: str

    def segment(self, nmap: NormalizedBeatmap, extractor: FeatureExtractor) -> list[Segment]:
        """Split a normalized map into segments with local feature vectors."""


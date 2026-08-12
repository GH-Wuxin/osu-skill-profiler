"""Fixed-hit-object-count segmentation."""

from __future__ import annotations

from ..features.extractor import FeatureExtractor
from ..parser.normalized import NormalizedBeatmap
from .base import Segment


class FixedObjectCountStrategy:
    """Consecutive chunks of a fixed number of hit objects."""

    name = "fixed_count"

    def __init__(self, chunk_size: int = 20) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.chunk_size = int(chunk_size)

    def segment(self, nmap: NormalizedBeatmap, extractor: FeatureExtractor) -> list[Segment]:
        objects = nmap.objects
        if not objects:
            return []
        segments: list[Segment] = []
        for start_idx in range(0, len(objects), self.chunk_size):
            end_idx = min(start_idx + self.chunk_size, len(objects))
            subset = nmap.slice(start_idx, end_idx)
            segments.append(
                Segment(
                    start_ms=objects[start_idx].time_ms,
                    end_ms=max(extractor.object_end_time_ms(obj) for obj in subset.objects),
                    start_idx=start_idx,
                    end_idx=end_idx,
                    features=extractor.extract(subset),
                )
            )
        return segments

"""Fixed-time-window segmentation."""

from __future__ import annotations

from ..features.extractor import FeatureExtractor
from ..parser.normalized import NormalizedBeatmap
from .base import Segment


class FixedTimeWindowStrategy:
    """Non-overlapping fixed-duration windows aligned to the first object.

    Windows without any object are omitted. Objects are assigned by start
    time; a segment's end time is the window boundary (clamped to map end).
    """

    name = "fixed_time"

    def __init__(self, window_ms: float = 5000.0) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self.window_ms = float(window_ms)

    def segment(self, nmap: NormalizedBeatmap, extractor: FeatureExtractor) -> list[Segment]:
        objects = nmap.objects
        if not objects:
            return []
        # Hit-object times can be out of file order in rare real maps. Segment
        # in time order so fixed windows are a true partition of the object
        # sequence (indices refer to positions in this time-sorted view).
        order = sorted(range(len(objects)), key=lambda idx: (objects[idx].time_ms, idx))
        sorted_objects = tuple(objects[idx] for idx in order)
        sorted_map = NormalizedBeatmap(beatmap=nmap.beatmap, objects=sorted_objects)
        start = sorted_objects[0].time_ms
        end = max(extractor.object_end_time_ms(obj) for obj in sorted_objects)
        # Bucket by window index so absurdly large timestamps cannot create an
        # unbounded loop; windows are still aligned to the earliest object.
        buckets: dict[int, list[int]] = {}
        for pos, obj in enumerate(sorted_objects):
            bucket = int((obj.time_ms - start) // self.window_ms)
            buckets.setdefault(bucket, []).append(pos)
        segments: list[Segment] = []
        for bucket in sorted(buckets):
            window_start = start + bucket * self.window_ms
            window_end = min(window_start + self.window_ms, end)
            indices = buckets[bucket]
            first, last = indices[0], indices[-1]
            subset = sorted_map.slice(first, last + 1)
            segments.append(
                Segment(
                    start_ms=window_start,
                    end_ms=window_end,
                    start_idx=first,
                    end_idx=last + 1,
                    features=extractor.extract(subset),
                )
            )
        return segments

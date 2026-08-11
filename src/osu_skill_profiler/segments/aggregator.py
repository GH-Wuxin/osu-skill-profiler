"""Map-level features produced by aggregating segment local features."""

from __future__ import annotations

import math

from .base import Segment
from ..features.stats import percentile


def _numeric_values(segments: list[Segment], key: str) -> list[float]:
    return [
        float(segment.features[key])
        for segment in segments
        if isinstance(segment.features.get(key), (int, float))
        and math.isfinite(float(segment.features[key]))
    ]


def aggregate_features(segments: list[Segment]) -> dict:
    """Aggregate per-segment features into a deterministic map-level dict.

    For every numeric feature present in at least one segment, emit mean, std,
    max and p90 across segments, plus the number of non-empty segments.
    """

    if not segments:
        return {"segment_count": 0}
    keys: list[str] = []
    for segment in segments:
        for key in segment.features:
            if key not in keys:
                keys.append(key)
    output: dict = {"segment_count": len(segments)}
    for key in keys:
        values = sorted(_numeric_values(segments, key))
        if not values:
            continue
        scale = max(abs(v) for v in values)
        if scale == 0:
            mean = 0.0
            std = 0.0
        else:
            mean = scale * (sum(v / scale for v in values) / len(values))
            std = scale * math.sqrt(sum(((v - mean) / scale) ** 2 for v in values) / len(values))
        output[f"{key}_mean"] = mean
        output[f"{key}_std"] = std
        output[f"{key}_max"] = values[-1]
        output[f"{key}_p90"] = percentile(values, 0.90)
    return output

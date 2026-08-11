"""Unified model interface.

Consumers interact only with ``analyze_map`` / ``analyze_segments`` and the
versioned JSON output. The internal implementation (heuristic, LightGBM,
ONNX, neural network, ...) is deliberately hidden behind this protocol.
"""

from __future__ import annotations

from typing import Protocol

from ..parser.normalized import NormalizedBeatmap


class SkillProfiler(Protocol):
    model_version: str
    taxonomy_version: str

    def analyze_map(self, source: str | NormalizedBeatmap) -> dict:
        """Return a versioned skill-profile JSON dict for one beatmap."""

    def analyze_segments(self, source: str | NormalizedBeatmap) -> list[dict]:
        """Return the raw segment representation for one beatmap."""


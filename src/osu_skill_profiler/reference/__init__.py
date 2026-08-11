"""Layer B — Official Reference Signal Layer (v0.1).

This package is intentionally isolated from ``features`` and ``signals``.
Normal local-signal extraction never imports this package, so the reference
layer can be disabled or omitted without changing observable Layer A
behaviour.

Everything emitted under ``ref.ppy.*`` is REFERENCE_ONLY evidence derived
from audited ppy/osu difficulty evaluator semantics (pinned upstream
``b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e``, difficulty version 20260706).
It is NOT feature ground truth, NOT a taxonomy label, NOT player skill and
NOT an official difficulty final.
"""

from .ppy.extractor import ReferenceSignalExtractor, segment_reference_signals

__all__ = ["ReferenceSignalExtractor", "segment_reference_signals"]

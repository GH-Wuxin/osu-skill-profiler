"""Versioned Local Signal layers.

Deterministic, gameplay-aware, per-object observable signals extracted from
parsed .osu beatmaps. This layer is independent of the frozen v0.1 feature
contract: v0.1 features are never modified by anything in this package.

Layers used by this package:

  A - observable local signals (allowed as model input features)
  B - official reference signals (only as ``official_reference.*``; never
      treated as ground truth).  This phase implements *no* Layer B finals.
  C - learned/interpretable skills (forbidden in this phase).
"""

from __future__ import annotations

LEGACY_SIGNAL_VERSION = "0.2.0"
PREVIOUS_SIGNAL_VERSION = "0.3.0"
SIGNAL_VERSION = "0.4.0"

__all__ = [
    "LEGACY_SIGNAL_VERSION",
    "PREVIOUS_SIGNAL_VERSION",
    "SIGNAL_VERSION",
]

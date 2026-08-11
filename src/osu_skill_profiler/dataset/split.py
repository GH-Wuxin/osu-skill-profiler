"""Deterministic, leakage-preventing dataset splits.

The default split is beatmapset-disjoint: every difficulty of the same
beatmapset stays in one fold. A mapper-disjoint split is provided for future
mapper-leakage checks. Splits never stratify randomly by difficulty.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Iterable


def _group_key(sample: dict, key: str) -> str:
    value = sample.get(key)
    if value is None:
        # Samples without a group id must never leak across folds; fall back
        # to the unique sample id, which makes every such sample its own group.
        return f"__ungrouped__:{sample.get('sample_id', '')}"
    return f"{key}:{value}"


def _group_samples(samples: list[dict], key: str) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for sample in samples:
        grouped.setdefault(_group_key(sample, key), []).append(sample)
    return [grouped[group_key] for group_key in sorted(grouped)]


def _split_groups(groups: list[list[dict]], train_ratio: float, seed: int) -> tuple[list[dict], list[dict]]:
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be strictly between 0 and 1")
    rng = random.Random(seed)
    shuffled = list(groups)
    rng.shuffle(shuffled)
    train_count = max(1, round(len(shuffled) * train_ratio))
    train_groups = shuffled[:train_count]
    test_groups = shuffled[train_count:]
    train = [sample for group in train_groups for sample in group]
    test = [sample for group in test_groups for sample in group]
    return train, test


def split_by_beatmapset(samples: list[dict], train_ratio: float = 0.8, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Split by beatmapset groups; the default, difficulty-independent split."""

    return _split_groups(_group_samples(samples, "beatmapset_id"), train_ratio, seed)


def split_by_mapper(samples: list[dict], train_ratio: float = 0.8, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Split by mapper groups; reserved for mapper-leakage checks."""

    return _split_groups(_group_samples(samples, "mapper"), train_ratio, seed)


def _ids(samples: Iterable[dict], key: str) -> set:
    return {_group_key(sample, key) for sample in samples}


def validate_disjoint_split(train: list[dict], test: list[dict], key: str = "beatmapset_id") -> list[str]:
    """Return a list of leakage violations (empty when the split is clean)."""

    overlap = _ids(train, key) & _ids(test, key)
    return [f"{key} group {value!r} appears in both folds" for value in sorted(overlap)]

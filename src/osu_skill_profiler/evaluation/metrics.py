"""Deterministic, dependency-free evaluation metrics.

These functions are pure: the same inputs always produce the same outputs.
They are meant to be used by a future evaluation pipeline once real labels
(human annotation or validated tournament metadata) and a trained model exist.
They contain no model code and no accuracy claims about this project.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional


class EvaluationError(ValueError):
    """Raised when metric inputs violate the evaluation contract."""


def _aligned_lists(y_true: Iterable[float], y_pred: Iterable[float]) -> tuple[list[float], list[float]]:
    true_list = [float(v) for v in y_true]
    pred_list = [float(v) for v in y_pred]
    if len(true_list) != len(pred_list):
        raise EvaluationError("y_true and y_pred must have the same length")
    if not true_list:
        raise EvaluationError("metric inputs must not be empty")
    return true_list, pred_list


def mae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Mean absolute error."""

    true_list, pred_list = _aligned_lists(y_true, y_pred)
    return sum(abs(t - p) for t, p in zip(true_list, pred_list)) / len(true_list)


def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Root mean squared error."""

    true_list, pred_list = _aligned_lists(y_true, y_pred)
    squared = sum((t - p) ** 2 for t, p in zip(true_list, pred_list))
    return math.sqrt(squared / len(true_list))


def pearson_r(y_true: Iterable[float], y_pred: Iterable[float]) -> Optional[float]:
    """Pearson correlation; None when either input is constant."""

    true_list, pred_list = _aligned_lists(y_true, y_pred)
    true_mean = sum(true_list) / len(true_list)
    pred_mean = sum(pred_list) / len(pred_list)
    numerator = sum((t - true_mean) * (p - pred_mean) for t, p in zip(true_list, pred_list))
    true_var = sum((t - true_mean) ** 2 for t in true_list)
    pred_var = sum((p - pred_mean) ** 2 for p in pred_list)
    denominator = math.sqrt(true_var * pred_var)
    if denominator == 0:
        return None
    return numerator / denominator


def kendall_tau(y_true: Iterable[float], y_pred: Iterable[float]) -> Optional[float]:
    """Kendall rank correlation tau-a with ties counted as neither.

    Returns None when there are no comparable (concordant/discordant) pairs.
    """

    true_list, pred_list = _aligned_lists(y_true, y_pred)
    concordant = 0
    discordant = 0
    for i in range(len(true_list)):
        for j in range(i + 1, len(true_list)):
            t_diff = true_list[i] - true_list[j]
            p_diff = pred_list[i] - pred_list[j]
            if t_diff == 0 or p_diff == 0:
                continue
            if (t_diff > 0) == (p_diff > 0):
                concordant += 1
            else:
                discordant += 1
    comparable = concordant + discordant
    if comparable == 0:
        return None
    return (concordant - discordant) / comparable


def accuracy(y_true: Iterable, y_pred: Iterable) -> float:
    """Fraction of exact matches between categorical predictions."""

    true_list = list(y_true)
    pred_list = list(y_pred)
    if len(true_list) != len(pred_list):
        raise EvaluationError("y_true and y_pred must have the same length")
    if not true_list:
        raise EvaluationError("metric inputs must not be empty")
    return sum(1 for t, p in zip(true_list, pred_list) if t == p) / len(true_list)


def balanced_accuracy(y_true: Iterable, y_pred: Iterable) -> float:
    """Unweighted mean of per-class recall; 0.0 when no class is present."""

    true_list = list(y_true)
    pred_list = list(y_pred)
    if len(true_list) != len(pred_list):
        raise EvaluationError("y_true and y_pred must have the same length")
    if not true_list:
        raise EvaluationError("metric inputs must not be empty")
    classes = sorted(set(true_list) | set(pred_list))
    recalls: list[float] = []
    for cls in classes:
        total = sum(1 for t in true_list if t == cls)
        if total == 0:
            continue
        correct = sum(1 for t, p in zip(true_list, pred_list) if t == cls and p == cls)
        recalls.append(correct / total)
    return sum(recalls) / len(recalls) if recalls else 0.0


def macro_f1(y_true: Iterable, y_pred: Iterable) -> float:
    """Unweighted mean of per-class F1; classes absent from prediction count as 0."""

    true_list = list(y_true)
    pred_list = list(y_pred)
    if len(true_list) != len(pred_list):
        raise EvaluationError("y_true and y_pred must have the same length")
    if not true_list:
        raise EvaluationError("metric inputs must not be empty")
    classes = sorted(set(true_list) | set(pred_list))
    f1_scores: list[float] = []
    for cls in classes:
        true_positive = sum(1 for t, p in zip(true_list, pred_list) if t == cls and p == cls)
        false_positive = sum(1 for t, p in zip(true_list, pred_list) if t != cls and p == cls)
        false_negative = sum(1 for t, p in zip(true_list, pred_list) if t == cls and p != cls)
        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
        if precision + recall == 0:
            f1_scores.append(0.0)
        else:
            f1_scores.append(2 * precision * recall / (precision + recall))
    return sum(f1_scores) / len(f1_scores)

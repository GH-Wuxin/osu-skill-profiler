"""Evaluation contracts for future trained models.

This package contains deterministic, dependency-free metrics only. The
project currently ships no trained skill model and no ground-truth labels, so
nothing in this package reports real model performance. It defines the
interfaces that a future evaluation pipeline can use once human labels and a
trained model exist.
"""

from .metrics import (
    accuracy,
    balanced_accuracy,
    kendall_tau,
    macro_f1,
    mae,
    pearson_r,
    rmse,
)

__all__ = [
    "accuracy",
    "balanced_accuracy",
    "kendall_tau",
    "macro_f1",
    "mae",
    "pearson_r",
    "rmse",
]

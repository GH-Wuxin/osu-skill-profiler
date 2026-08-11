import unittest

from osu_skill_profiler.evaluation import (
    accuracy,
    balanced_accuracy,
    kendall_tau,
    macro_f1,
    mae,
    pearson_r,
    rmse,
)
from osu_skill_profiler.evaluation.metrics import EvaluationError


class RegressionMetricsTests(unittest.TestCase):
    def test_mae_and_rmse_known_values(self):
        self.assertEqual(mae([1.0, 2.0, 3.0], [2.0, 2.0, 2.0]), 2.0 / 3.0)
        self.assertAlmostEqual(rmse([1.0, 2.0, 3.0], [2.0, 2.0, 2.0]), (2.0 / 3.0) ** 0.5)

    def test_perfect_prediction_zero_error(self):
        values = [0.0, 1.0, 2.0, 5.0]
        self.assertEqual(mae(values, values), 0.0)
        self.assertEqual(rmse(values, values), 0.0)
        self.assertEqual(pearson_r(values, values), 1.0)

    def test_pearson_negative_correlation(self):
        y_true = [0.0, 1.0, 2.0, 3.0]
        y_pred = [3.0, 2.0, 1.0, 0.0]
        self.assertAlmostEqual(pearson_r(y_true, y_pred), -1.0)

    def test_constant_input_correlation_is_none(self):
        self.assertIsNone(pearson_r([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]))

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(EvaluationError):
            mae([1.0], [1.0, 2.0])
        with self.assertRaises(EvaluationError):
            rmse([], [])


class RankingMetricsTests(unittest.TestCase):
    def test_perfect_ranking_tau_one(self):
        self.assertEqual(kendall_tau([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]), 1.0)

    def test_reversed_ranking_tau_minus_one(self):
        self.assertEqual(kendall_tau([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]), -1.0)

    def test_ties_are_neither(self):
        self.assertEqual(kendall_tau([1.0, 1.0, 2.0], [1.0, 1.0, 2.0]), 1.0)


class ClassificationMetricsTests(unittest.TestCase):
    def test_accuracy(self):
        self.assertEqual(accuracy(["a", "b", "a"], ["a", "b", "b"]), 2.0 / 3.0)

    def test_balanced_accuracy_ignores_missing_class(self):
        y_true = ["a", "a", "a", "b"]
        y_pred = ["a", "a", "a", "a"]
        self.assertAlmostEqual(balanced_accuracy(y_true, y_pred), 0.5)

    def test_macro_f1(self):
        y_true = ["a", "a", "b", "b", "c"]
        y_pred = ["a", "b", "b", "b", "c"]
        # a: precision 1.0, recall 0.5 -> 2/3 ; b: precision 2/3, recall 1.0 -> 0.8 ; c: 1.0
        self.assertAlmostEqual(macro_f1(y_true, y_pred), (2.0 / 3.0 + 0.8 + 1.0) / 3.0)

    def test_metric_input_validation(self):
        with self.assertRaises(EvaluationError):
            accuracy([], [])
        with self.assertRaises(EvaluationError):
            balanced_accuracy(["a"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()

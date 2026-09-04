from __future__ import annotations

import math
from pathlib import Path
import random
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import axis_support_frontier_v01 as linear  # noqa: E402
from map_demand_v01 import axis_support_frontier_v02 as powered  # noqa: E402


def samples_for(stars_and_counts: list[tuple[float, int]]) -> list[powered.SupportSample]:
    result: list[powered.SupportSample] = []
    time_ms = 0.0
    for star, count in stars_and_counts:
        rate = 5.0 + star * 1.30
        duration_ms = 1000.0 / rate
        for _ in range(count):
            time_ms += duration_ms
            result.append(
                powered.SupportSample(
                    star,
                    time_ms,
                    duration_ms,
                    episode_id=0,
                    section_id=0,
                    weight=1.0,
                )
            )
    return result


def establishment_oracle(
    samples: list[powered.SupportSample],
    policy: powered.SupportPolicy,
) -> tuple[float, float]:
    best_threshold = 0.0
    best_star = -1.0
    for threshold in sorted({sample.difficulty for sample in samples}, reverse=True):
        max_run_weight = 0.0
        for episode in {(sample.section_id, sample.episode_id) for sample in samples}:
            episode_samples = sorted(
                (
                    sample
                    for sample in samples
                    if (sample.section_id, sample.episode_id) == episode
                ),
                key=lambda sample: sample.time_ms,
            )
            run_weight = 0.0
            for sample in episode_samples:
                if sample.difficulty >= threshold and sample.weight > 0.0:
                    run_weight += sample.weight
                    max_run_weight = max(max_run_weight, run_weight)
                else:
                    run_weight = 0.0
        support = min(1.0, max_run_weight / policy.establishment_target_weight)
        ratio = min(1.0, support / policy.frontier_support_target)
        star = threshold * ratio**policy.partial_support_exponent
        if star > best_star:
            best_threshold = threshold
            best_star = star
    return best_threshold, best_star


def component_oracle(
    samples: list[powered.SupportSample],
    policy: powered.SupportPolicy,
    component: str,
) -> tuple[float, float]:
    best_threshold = 0.0
    best_star = -1.0
    for threshold in sorted({sample.difficulty for sample in samples}, reverse=True):
        best_weight = 0.0
        best_active_ms = 0.0
        episodes = {(sample.section_id, sample.episode_id) for sample in samples}
        for episode in episodes:
            episode_samples = sorted(
                (
                    sample
                    for sample in samples
                    if (sample.section_id, sample.episode_id) == episode
                ),
                key=lambda sample: sample.time_ms,
            )
            run_weight = 0.0
            run_active_ms = 0.0
            for sample in episode_samples:
                if sample.difficulty >= threshold and sample.weight > 0.0:
                    run_weight += sample.weight
                    run_active_ms += (
                        max(sample.duration_ms, policy.point_duration_ms)
                        * sample.weight
                    )
                    best_weight = max(best_weight, run_weight)
                    best_active_ms = max(best_active_ms, run_active_ms)
                else:
                    run_weight = 0.0
                    run_active_ms = 0.0
        support = min(
            1.0,
            best_weight / policy.establishment_target_weight
            if component == "establishment"
            else best_active_ms / policy.sustain_target_ms,
        )
        ratio = min(1.0, support / policy.frontier_support_target)
        star = threshold * ratio**policy.partial_support_exponent
        if star > best_star:
            best_threshold = threshold
            best_star = star
    return best_threshold, best_star


class PoweredSupportFrontierTests(unittest.TestCase):
    def test_powered_objective_selects_winner_during_threshold_scan(self):
        samples = samples_for([(15.0, 5), (6.6, 6)])
        result = powered.evaluate_support_frontier(
            samples,
            powered.RAW_SPEED_SUPPORT_POLICY,
        )
        threshold, expected = establishment_oracle(
            samples,
            powered.RAW_SPEED_SUPPORT_POLICY,
        )

        self.assertAlmostEqual(threshold, 6.6)
        self.assertAlmostEqual(
            result["establishment"]["winning_threshold_star"],
            threshold,
        )
        self.assertAlmostEqual(
            result["establishment"]["frontier_star"],
            expected,
        )
        self.assertAlmostEqual(expected, 5.2579688492494645)

    def test_linear_policy_replays_v01_frontier_values(self):
        samples = samples_for([(12.0, 3), (8.0, 8), (5.0, 10)])
        old_samples = [
            linear.SupportSample(
                sample.difficulty,
                sample.time_ms,
                sample.duration_ms,
                sample.episode_id,
                sample.section_id,
                sample.weight,
            )
            for sample in samples
        ]
        old = linear.evaluate_support_frontier(
            old_samples,
            linear.RAW_SPEED_SUPPORT_POLICY,
        )
        policy = powered.SupportPolicy(
            name="raw_speed",
            establishment_target_weight=16.0,
            sustain_target_ms=1200.0,
            recurrence_target_episodes=2.0,
            recurrence_min_episode_weight=2.0,
            point_duration_ms=50.0,
            frontier_support_target=0.8,
            establishment_mix=0.62,
            sustain_mix=0.23,
            recurrence_mix=0.15,
            recurrence_scope="episode",
            partial_support_exponent=1.0,
        )
        new = powered.evaluate_support_frontier(samples, policy)

        for component in ("establishment", "sustain", "recurrence"):
            with self.subTest(component=component):
                self.assertEqual(
                    new[component]["winning_threshold_star"],
                    old[component]["winning_threshold_star"],
                )
                self.assertEqual(
                    new[component]["frontier_star"],
                    old[component]["frontier_star"],
                )
                self.assertEqual(
                    new[component]["support"],
                    old[component]["support"],
                )
        self.assertEqual(new["combined_frontier_star"], old["combined_frontier_star"])

    def test_powered_establishment_and_sustain_match_independent_oracle(self):
        generator = random.Random(91017)
        for case in range(80):
            samples: list[powered.SupportSample] = []
            time_ms = 0.0
            for index in range(generator.randint(6, 40)):
                difficulty = generator.choice((0.0, 2.5, 4.0, 6.6, 9.0, 15.0))
                duration_ms = generator.choice((25.0, 50.0, 75.0, 120.0))
                time_ms += duration_ms
                samples.append(
                    powered.SupportSample(
                        difficulty,
                        time_ms,
                        duration_ms,
                        episode_id=index // generator.randint(4, 9),
                        section_id=0,
                        weight=generator.choice((0.0, 0.25, 0.6, 1.0)),
                    )
                )
            result = powered.evaluate_support_frontier(
                samples,
                powered.RAW_SPEED_SUPPORT_POLICY,
            )
            for component in ("establishment", "sustain"):
                threshold, star = component_oracle(
                    samples,
                    powered.RAW_SPEED_SUPPORT_POLICY,
                    component,
                )
                with self.subTest(case=case, component=component):
                    self.assertEqual(
                        result[component]["winning_threshold_star"],
                        threshold,
                    )
                    self.assertAlmostEqual(
                        result[component]["frontier_star"],
                        star,
                    )

    def test_policy_rejects_invalid_exponent(self):
        for exponent in (0.5, math.inf, math.nan):
            with self.subTest(exponent=exponent):
                with self.assertRaises(ValueError):
                    powered.SupportPolicy(partial_support_exponent=exponent)


if __name__ == "__main__":
    unittest.main()

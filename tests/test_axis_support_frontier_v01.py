from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import axis_support_frontier_v01 as frontier  # noqa: E402


def hard_mode(
    count: int,
    *,
    difficulty: float = 12.0,
    episode_id: object = "hard-0",
    section_id: object = "section-0",
    start_ms: float = 0.0,
    spacing_ms: float = 100.0,
    duration_ms: float = 100.0,
    weight: float = 1.0,
) -> list[frontier.SupportSample]:
    return [
        frontier.SupportSample(
            difficulty=difficulty,
            time_ms=start_ms + index * spacing_ms,
            duration_ms=duration_ms,
            episode_id=episode_id,
            section_id=section_id,
            weight=weight,
        )
        for index in range(count)
    ]


class SupportFrontierV01Tests(unittest.TestCase):
    def test_slow_filler_does_not_lend_support_to_hard_mode(self) -> None:
        hard = hard_mode(8)
        baseline = frontier.evaluate_support_frontier(
            hard,
            frontier.JUMP_SUPPORT_POLICY,
        )
        slow_filler = [
            frontier.SupportSample(
                difficulty=0.25,
                time_ms=10_000.0 + index * 500.0,
                duration_ms=400.0,
                episode_id=f"easy-{index}",
                section_id="easy-filler",
            )
            for index in range(500)
        ]
        filled = frontier.evaluate_support_frontier(
            [*hard, *slow_filler],
            frontier.JUMP_SUPPORT_POLICY,
        )

        self.assertEqual(filled["physical_peak"], baseline["physical_peak"])
        self.assertEqual(
            filled["establishment"]["frontier_star"],
            baseline["establishment"]["frontier_star"],
        )
        self.assertEqual(
            filled["establishment"]["winning_threshold_star"],
            baseline["establishment"]["winning_threshold_star"],
        )

    def test_extending_same_hard_mode_raises_establishment_and_sustain(self) -> None:
        short = frontier.evaluate_support_frontier(
            hard_mode(8),
            frontier.JUMP_SUPPORT_POLICY,
        )
        long = frontier.evaluate_support_frontier(
            hard_mode(16),
            frontier.JUMP_SUPPORT_POLICY,
        )

        self.assertEqual(short["physical_peak"], long["physical_peak"])
        self.assertLess(
            short["establishment"]["frontier_star"],
            long["establishment"]["frontier_star"],
        )
        self.assertLess(
            short["sustain"]["frontier_star"],
            long["sustain"]["frontier_star"],
        )
        self.assertLess(
            short["establishment"]["support"],
            long["establishment"]["support"],
        )
        self.assertLess(short["sustain"]["support"], long["sustain"]["support"])

    def test_separated_repeat_raises_recurrence_without_changing_peak(self) -> None:
        first = hard_mode(6, difficulty=10.5, episode_id="burst-a")
        once = frontier.evaluate_support_frontier(first, frontier.RAW_SPEED_SUPPORT_POLICY)
        repeated = frontier.evaluate_support_frontier(
            [
                *first,
                *hard_mode(
                    6,
                    difficulty=10.5,
                    episode_id="burst-b",
                    section_id="section-1",
                    start_ms=20_000.0,
                ),
            ],
            frontier.RAW_SPEED_SUPPORT_POLICY,
        )

        self.assertEqual(once["physical_peak"], repeated["physical_peak"])
        self.assertEqual(once["recurrence"]["frontier_star"], 0.0)
        self.assertGreater(
            repeated["recurrence"]["frontier_star"],
            once["recurrence"]["frontier_star"],
        )
        self.assertGreater(repeated["recurrence"]["recurrence_units"], 0.0)

    def test_six_pair_raw_burst_is_not_a_fully_established_stream(self) -> None:
        burst = frontier.evaluate_support_frontier(
            hard_mode(6, difficulty=11.0),
            frontier.RAW_SPEED_SUPPORT_POLICY,
        )
        established = frontier.evaluate_support_frontier(
            hard_mode(16, difficulty=11.0),
            frontier.RAW_SPEED_SUPPORT_POLICY,
        )

        self.assertLess(burst["establishment"]["frontier_star"], burst["physical_peak"])
        self.assertEqual(established["establishment"]["frontier_star"], 11.0)
        self.assertGreater(
            established["establishment"]["frontier_star"],
            burst["establishment"]["frontier_star"],
        )

    def test_below_threshold_intervals_split_one_caller_episode(self) -> None:
        samples: list[frontier.SupportSample] = []
        time_ms = 0.0
        for _ in range(3):
            samples.extend(
                hard_mode(
                    4,
                    difficulty=12.0,
                    episode_id="same-parser-block",
                    start_ms=time_ms,
                    spacing_ms=50.0,
                    duration_ms=50.0,
                )
            )
            time_ms += 200.0
            samples.append(
                frontier.SupportSample(
                    difficulty=1.0,
                    time_ms=time_ms,
                    duration_ms=500.0,
                    episode_id="same-parser-block",
                    section_id="section-0",
                )
            )
            time_ms += 500.0

        result = frontier.evaluate_support_frontier(
            samples,
            frontier.RAW_SPEED_SUPPORT_POLICY,
        )

        # Twelve fast pairs exist globally, but never as one contiguous run.
        # The ordinary intervals must prevent them claiming full establishment.
        self.assertEqual(
            result["establishment"]["winning_episode_sample_count"], 4
        )
        self.assertLess(
            result["establishment"]["frontier_star"],
            result["physical_peak"],
        )
        self.assertGreater(result["recurrence"]["frontier_star"], 0.0)

    def test_confidence_is_metadata_and_never_scales_physical_or_frontier(self) -> None:
        samples = hard_mode(12, difficulty=11.25)
        low = frontier.evaluate_support_frontier(
            samples,
            frontier.JUMP_SUPPORT_POLICY,
            evidence_confidence=0.15,
        )
        high = frontier.evaluate_support_frontier(
            samples,
            frontier.JUMP_SUPPORT_POLICY,
            evidence_confidence=0.95,
        )

        self.assertEqual(low["evidence_confidence"], 0.15)
        self.assertEqual(high["evidence_confidence"], 0.95)
        for key in (
            "physical_peak",
            "establishment",
            "sustain",
            "recurrence",
            "combined_frontier_star",
            "combined_support",
        ):
            self.assertEqual(low[key], high[key])
        self.assertFalse(low["diagnostics"]["confidence_affects_frontier"])

    def test_frontier_is_unbounded_and_does_not_clip_above_ten(self) -> None:
        result = frontier.evaluate_support_frontier(
            hard_mode(24, difficulty=14.75),
            frontier.JUMP_SUPPORT_POLICY,
        )

        self.assertEqual(result["physical_peak"], 14.75)
        self.assertEqual(result["establishment"]["frontier_star"], 14.75)
        self.assertGreater(result["combined_frontier_star"], 10.0)
        self.assertGreater(result["sustain"]["frontier_star"], 10.0)

    def test_weight_affects_support_but_not_physical_peak(self) -> None:
        samples = [
            frontier.SupportSample(20.0, 0.0, 50.0, "unsupported", "s0", 0.0),
            *hard_mode(16, difficulty=9.0, episode_id="supported", section_id="s1"),
        ]
        result = frontier.evaluate_support_frontier(samples, frontier.JUMP_SUPPORT_POLICY)

        self.assertEqual(result["physical_peak"], 20.0)
        self.assertEqual(result["establishment"]["frontier_star"], 9.0)
        self.assertEqual(result["establishment"]["winning_threshold_star"], 9.0)

    def test_time_duration_episode_and_section_are_reported(self) -> None:
        samples = hard_mode(
            5,
            difficulty=8.0,
            episode_id="episode-7",
            section_id="section-3",
            start_ms=1_000.0,
            spacing_ms=150.0,
            duration_ms=90.0,
        )
        result = frontier.evaluate_support_frontier(samples)
        winning = result["sustain"]

        self.assertEqual(winning["winning_episode_id"], "episode-7")
        self.assertEqual(winning["winning_section_id"], "section-3")
        self.assertEqual(winning["winning_episode_start_ms"], 1_000.0)
        self.assertEqual(winning["winning_episode_end_ms"], 1_690.0)
        self.assertEqual(winning["winning_episode_active_ms"], 450.0)
        self.assertEqual(winning["episode_count"], 1)
        self.assertEqual(winning["section_count"], 1)

    def test_mapping_samples_and_all_observed_thresholds_are_supported(self) -> None:
        result = frontier.evaluate_support_frontier(
            [
                {
                    "difficulty": 7.0,
                    "time_ms": 0.0,
                    "duration_ms": 100.0,
                    "episode_id": "a",
                    "section_id": "s",
                },
                {
                    "difficulty": 5.0,
                    "time_ms": 100.0,
                    "duration_ms": 100.0,
                    "episode_id": "a",
                    "section_id": "s",
                },
            ]
        )

        self.assertEqual(result["threshold_count"], 2)
        self.assertEqual(result["physical_peak"], 7.0)
        self.assertEqual(result["valid_sample_count"], 2)

    def test_empty_and_non_finite_inputs_are_structurally_safe(self) -> None:
        empty = frontier.evaluate_support_frontier([])
        self.assertEqual(empty["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(empty["physical_peak"])
        self.assertIsNone(empty["establishment"]["frontier_star"])

        invalid = frontier.evaluate_support_frontier(
            [
                frontier.SupportSample(math.nan, 0.0),
                frontier.SupportSample(8.0, math.inf),
                frontier.SupportSample(8.0, 0.0, math.nan),
                frontier.SupportSample(8.0, 0.0, 0.0, weight=math.inf),
                object(),
            ],
            evidence_confidence=math.nan,
        )
        self.assertEqual(invalid["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(invalid["physical_peak"])
        self.assertEqual(invalid["ignored_sample_count"], 5)
        self.assertEqual(invalid["evidence_confidence"], 0.0)

    def test_policy_presets_are_explicit_and_validate_configuration(self) -> None:
        self.assertEqual(frontier.JUMP_SUPPORT_POLICY.name, "jump")
        self.assertEqual(frontier.RAW_SPEED_SUPPORT_POLICY.name, "raw_speed")
        self.assertEqual(
            frontier.JUMP_SUPPORT_POLICY.establishment_target_weight, 16.0
        )
        self.assertEqual(
            frontier.RAW_SPEED_SUPPORT_POLICY.establishment_target_weight, 16.0
        )
        self.assertNotEqual(
            frontier.JUMP_SUPPORT_POLICY.sustain_target_ms,
            frontier.RAW_SPEED_SUPPORT_POLICY.sustain_target_ms,
        )
        with self.assertRaises(ValueError):
            frontier.SupportPolicy(frontier_support_target=0.0)
        with self.assertRaises(ValueError):
            frontier.SupportPolicy(recurrence_scope="object")

    def test_public_frontier_selection_is_explicit_and_confidence_free(self) -> None:
        envelope = frontier.evaluate_support_frontier(
            [
                frontier.SupportSample(
                    difficulty=12.0,
                    time_ms=episode * 1000.0 + index * 60.0,
                    duration_ms=60.0,
                    episode_id=episode,
                    weight=1.0,
                )
                for episode in range(3)
                for index in range(4)
            ],
            evidence_confidence=0.01,
        )
        selected = frontier.select_public_frontier(
            envelope,
            components=("establishment", "recurrence"),
            policy_id="TEST_MAX_ER",
        )

        self.assertEqual(selected["selected_component"], "recurrence")
        self.assertEqual(
            selected["frontier_star"],
            envelope["recurrence"]["frontier_star"],
        )
        self.assertFalse(selected["confidence_affects_selection"])
        self.assertFalse(selected["physical_peak_is_candidate"])
        self.assertNotIn("sustain", selected["eligible_components"])


if __name__ == "__main__":
    unittest.main()

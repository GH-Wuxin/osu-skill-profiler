from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01.type_classifier_v01 import propose_type_annotations  # noqa: E402


class FakeObject:
    def __init__(
        self,
        index: int,
        *,
        delta: float,
        distance: float,
        angle: float,
        object_type: str = "circle",
        slider_length: float | None = None,
        repeat_count: int = 0,
        bpm: float | None = None,
        x: float | None = None,
        y: float | None = None,
        slider_velocity: float | None = None,
    ) -> None:
        self.time_ms = index * delta
        self.delta_time_ms = None if index == 0 else delta
        self.distance_from_previous = None if index == 0 else distance
        self.movement_velocity_norm_per_s = None if index == 0 else distance / (delta / 1000.0)
        self.angle_deg = None if index in {0, 29} else angle
        self.local_bpm = bpm if bpm is not None else 60000.0 / max(1.0, delta * 2.0)
        self.local_sv = 1.0 + (0.45 if object_type == "slider" and index % 3 == 0 else 0.0)
        self.local_density_per_s = 1000.0 / delta
        self.slider_repeat_count = repeat_count if object_type == "slider" else None
        self.slider_velocity_px_per_s = slider_velocity if object_type == "slider" else None
        self.x_norm = (x if x is not None else 64.0 + (index % 8) * 48.0) / 512.0
        self.y_norm = (y if y is not None else 72.0 + (index % 5) * 44.0) / 384.0
        self.raw = SimpleNamespace(
            object_type=object_type,
            slider_pixel_length=slider_length,
        )

    def canonical_end_time_ms(self) -> float:
        return self.time_ms + (240.0 if self.raw.object_type == "slider" else 0.0)


def section_for(objects: tuple[FakeObject, ...], section_id: str = "s1") -> dict:
    return {
        "section_id": section_id,
        "start_ms": objects[0].time_ms,
        "end_ms": objects[-1].canonical_end_time_ms(),
        "object_start": 0,
        "object_end": len(objects),
        "stats": {"objects": len(objects)},
    }


class TypeProposalTests(unittest.TestCase):
    def test_regular_large_spacing_is_proposed_as_jump(self):
        objects = tuple(
            FakeObject(i, delta=180.0, distance=0.58, angle=150.0)
            for i in range(30)
        )
        sections, summary = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.5, "CircleSize": 4.0}
        )
        self.assertEqual(sections[0]["machine_proposal"]["primary_type"], "JUMP")
        self.assertEqual(summary["primary_type"], "JUMP")

    def test_long_fast_circle_chain_is_proposed_as_stream(self):
        objects = tuple(
            FakeObject(i, delta=82.0, distance=0.18, angle=35.0)
            for i in range(30)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.5, "CircleSize": 4.0}
        )
        proposal = sections[0]["machine_proposal"]
        self.assertEqual(proposal["primary_type"], "STREAM")
        self.assertGreaterEqual(proposal["scores"]["STREAM"], proposal["scores"]["JUMP"])

    def test_slider_heavy_irregular_section_is_not_forced_to_jump(self):
        objects = tuple(
            FakeObject(
                i,
                delta=155.0 if i % 3 else 235.0,
                distance=0.18 if i % 2 else 0.42,
                angle=25.0 if i % 2 else 150.0,
                object_type="slider" if i % 3 else "circle",
                slider_length=360.0,
                repeat_count=1,
                slider_velocity=720.0,
            )
            for i in range(30)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 8.5, "CircleSize": 4.0}
        )
        proposal = sections[0]["machine_proposal"]
        self.assertIn("TECH", [proposal["primary_type"], *proposal["secondary_types"]])
        self.assertIn("SLIDER_TECH", proposal["structural_tags"])

    def test_ez_adds_reading_proposal_without_erasing_structure(self):
        objects = tuple(
            FakeObject(i, delta=180.0, distance=0.55, angle=150.0)
            for i in range(30)
        )
        sections, _ = propose_type_annotations(
            objects,
            [section_for(objects)],
            {"ApproachRate": 4.75, "CircleSize": 2.0},
            ["EZ"],
        )
        proposal = sections[0]["machine_proposal"]
        self.assertIn("JUMP", [proposal["primary_type"], *proposal["secondary_types"]])
        self.assertIn("GIMMICK", [proposal["primary_type"], *proposal["secondary_types"]])
        self.assertEqual(proposal["gimmick_subtype"], "EZ_READING")

    def test_ordinary_stream_spacing_is_not_overlap_or_burst(self):
        objects = tuple(
            FakeObject(
                i,
                delta=75.0,
                distance=0.14,
                angle=35.0,
                bpm=200.0,
                x=80.0 + (i % 7) * 52.0,
                y=90.0 + (i % 4) * 55.0,
            )
            for i in range(36)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.5, "CircleSize": 4.0}
        )
        proposal = sections[0]["machine_proposal"]
        self.assertEqual(proposal["primary_type"], "STREAM")
        self.assertNotIn("GIMMICK", proposal["secondary_types"])
        self.assertNotIn("BURST_HEAVY", proposal["structural_tags"])

    def test_regular_stacked_triplets_do_not_force_gimmick(self):
        objects = tuple(
            FakeObject(
                i,
                delta=87.0,
                distance=0.0 if i % 3 else 0.55,
                angle=80.0,
                bpm=172.0,
                x=120.0 + (i // 3 % 4) * 85.0,
                y=180.0,
            )
            for i in range(36)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.6, "CircleSize": 4.0}
        )
        proposal = sections[0]["machine_proposal"]
        self.assertNotEqual(proposal["primary_type"], "GIMMICK")
        self.assertNotIn("GIMMICK", proposal["secondary_types"])
        self.assertIsNone(proposal["gimmick_subtype"])

    def test_binary_half_to_quarter_is_not_speed_change(self):
        deltas = [150.0] * 8 + [75.0] * 8
        objects = tuple(
            FakeObject(i, delta=delta, distance=0.24, angle=70.0, bpm=200.0)
            for i, delta in enumerate(deltas)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.2, "CircleSize": 4.0}
        )
        self.assertNotIn("SPEED_CHANGE", sections[0]["machine_proposal"]["structural_tags"])

    def test_binary_to_triplet_is_speed_change(self):
        deltas = [75.0] * 8 + [100.0] * 8
        objects = tuple(
            FakeObject(i, delta=delta, distance=0.24, angle=70.0, bpm=200.0)
            for i, delta in enumerate(deltas)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.2, "CircleSize": 4.0}
        )
        self.assertIn("SPEED_CHANGE", sections[0]["machine_proposal"]["structural_tags"])

    def test_regular_large_jumps_are_not_separation(self):
        distances = [0.58] * 10 + [0.78] + [0.58] * 10
        objects = tuple(
            FakeObject(i, delta=180.0, distance=distance, angle=150.0)
            for i, distance in enumerate(distances)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 9.5, "CircleSize": 4.0}
        )
        self.assertNotIn("SEPARATION", sections[0]["machine_proposal"]["structural_tags"])

    def test_slow_plain_sliders_do_not_become_tech(self):
        objects = tuple(
            FakeObject(
                i,
                delta=240.0,
                distance=0.22,
                angle=100.0,
                object_type="slider",
                slider_length=180.0,
                slider_velocity=180.0,
            )
            for i in range(24)
        )
        sections, _ = propose_type_annotations(
            objects, [section_for(objects)], {"ApproachRate": 8.5, "CircleSize": 4.0}
        )
        proposal = sections[0]["machine_proposal"]
        self.assertNotEqual(proposal["primary_type"], "TECH")
        self.assertNotIn("SLIDER_TECH", proposal["structural_tags"])


if __name__ == "__main__":
    unittest.main()

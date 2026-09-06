"""Circle spatial-reentry contracts; no map-rating or ranking targets.

All spatial cases are extracted from actual in-memory osu! objects. The
standalone scorer checks isolate its local ownership and evidence rules;
public extraction checks cover the final integration separately.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "tools", ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01 import flow_execution_v02 as flow
from map_demand_v01 import flow_geometry_v02 as geometry
from map_demand_v01 import flow_spatial_reentry_v01 as detector
from map_demand_v01 import flow_reentry_execution_v01 as reentry
from map_demand_v01 import paired_transition_geometry_v01 as paired
from test_flow_execution_v02 import extract_rows
from osu_skill_profiler.parser.osu_parser import parse_osu
from osu_skill_profiler.signals.extractor import LocalSignalExtractor


def two_phrases(bridge=108.0, left_scale=1.0, right_scale=1.0):
    points = [(100.0, 100.0)]
    for x, y in ((30, 0), (25, 15), (15, 25)):
        points.append((points[-1][0] + left_scale*x, points[-1][1] + left_scale*y))
    norm = math.hypot(100, 40)
    points.append((points[-1][0] + bridge*100/norm, points[-1][1] + bridge*40/norm))
    for x, y in ((-10, 30), (-25, 20), (-30, 0)):
        points.append((points[-1][0] + right_scale*x, points[-1][1] + right_scale*y))
    assert all(0 <= x <= 512 and 0 <= y <= 384 for x, y in points)
    return points


def curved_points(turn=math.pi/6, distances=None):
    x, y, heading = 170.0, 100.0, 0.0
    points = [(x, y)]
    for distance in distances or [30.0]*7:
        x += distance*math.cos(heading)
        y += distance*math.sin(heading)
        heading += turn
        points.append((x, y))
    return points


def three_phrases():
    points = [(50.0, 50.0)]
    vectors = [(30,0),(25,15),(15,25),(150,20),(-10,30),(-25,20),(-30,0),(0,100),(30,0),(25,15),(15,25)]
    for x,y in vectors:
        points.append((points[-1][0]+x, points[-1][1]+y))
    assert all(0 <= x <= 512 and 0 <= y <= 384 for x,y in points)
    return points


def weak_high_flank_between_cheap_phrases():
    # Three 200px moves fit inside the field and turn by 89 degrees, yielding
    # TWO high-intensity but weak-forward links. Both spatial bridges stay
    # on the same 50ms tapping rhythm. Cheap outer phrases cannot establish
    # the high-intensity part merely by supplying a large total link mass.
    points = [(30.0+4*index,300.0) for index in range(5)]
    points.append((280.0,50.0))
    for index in range(3):
        heading = math.radians(89*index)
        points.append((points[-1][0]+200*math.cos(heading),points[-1][1]+200*math.sin(heading)))
    points.extend((60.0+4*index,30.0) for index in range(5))
    assert all(0 <= x <= 512 and 0 <= y <= 384 for x,y in points)
    return points


def separated_events_with_middle_motion():
    # Both event contexts end before/start after middle transition 8, even
    # at the detector's maximum four movements per side. A rest inserted
    # there must therefore be found by full-span continuity, not event-only
    # rhythm evidence.
    points = [(50.0,50.0)]
    vectors = [(30,0),(25,15),(15,25),(150,20),(-10,30),(-25,20),(-30,0)]
    vectors += [(30*math.cos(math.radians(angle)),30*math.sin(math.radians(angle))) for angle in (210,240,270,300,330,0)]
    for x,y in vectors:
        points.append((points[-1][0]+x,points[-1][1]+y))
    points.append((75.0,240.0))
    for x,y in ((30,0),(25,15),(15,25)):
        points.append((points[-1][0]+x,points[-1][1]+y))
    assert all(0 <= x <= 512 and 0 <= y <= 384 for x,y in points)
    return points


def actual_slider_rows(points, slider_at):
    objects = []
    for index, (x, y) in enumerate(points):
        suffix = f"2,0,L|{x+10:.15g}:{y:.15g},1,10" if index == slider_at else "1,0"
        objects.append(f"{x:.15g},{y:.15g},{1000+index*100},{suffix}")
    text = (
        "osu file format v14\n[General]\nMode:0\n[Metadata]\nTitle:Circle reentry\nArtist:Test\nCreator:Test\nVersion:Test\n"
        "[Difficulty]\nCircleSize:4\nApproachRate:9\nOverallDifficulty:8\nHPDrainRate:5\nSliderMultiplier:1.4\nSliderTickRate:1\n"
        "[TimingPoints]\n0,400,4,2,1,100,1,0\n[HitObjects]\n" + "\n".join(objects) + "\n"
    )
    beatmap = parse_osu(text)
    rows = LocalSignalExtractor().extract(beatmap)["objects"]
    return [{**row, "v091.start_x_px": obj.x, "v091.start_y_px": obj.y} for row, obj in zip(rows, beatmap.hit_objects)]


def scorer_inputs(rows):
    bundle = geometry.build_flow_geometry(rows)
    evidence = detector.extract_spatial_reentry_evidence(bundle)
    records = {}
    for transition in bundle["transitions"]:
        phase = transition["channels"][paired.FULL_PATH_FULL_TIME]
        radius = transition["radius_px"]
        if not phase["available"] or not radius or not transition["jump_phase_vector_available"]:
            continue
        records[transition["transition_index"]] = {
            "transition_index": transition["transition_index"],
            "source_index": transition["to_source_row_index"],
            "start_time_ms": transition["start_time_ms"], "time": transition["end_time_ms"],
            "distance": phase["distance_px"], "time_ms": phase["time_ms"], "radius": radius,
            "intensity": flow.execution_intensity(phase["distance_px"], phase["time_ms"], radius),
            "block": transition["block"], "segment": transition["segment"], "run": transition["block"],
        }
    return evidence, records


def isolated_score(rows, *, fixed_main_context=False):
    evidence, records = scorer_inputs(rows)
    if fixed_main_context:
        evidence["events"] = [event for event in evidence["events"] if event["bridge"]["from_source_row_index"] == 3]
        for event in evidence["events"]:
            event["contexts"] = [context for context in event["contexts"] if context["context_id"] == "L3R3"]
    # Explicit zero baseline isolates the NEW requirement, preventing the
    # existing ordinary Flow score from hiding an incorrect extra increment.
    return reentry.build_reentry_candidates(evidence, records, lambda *args: None)


def main_event(result, context_id="L3R3"):
    return next(
        candidate["events"][0] for candidate in result["candidates"]
        if candidate["distinct_reentry_count"] == 1
        and candidate["events"][0]["context"]["left"]["source_index_last"] == 3
        and candidate["events"][0]["context_id"] == context_id
    )


class FlowReentryLocalContractTests(unittest.TestCase):
    def test_one_short_genuine_reentry_has_finite_bounded_support(self):
        result = isolated_score(extract_rows(two_phrases()))
        winner = result["winner"]
        self.assertIsNotNone(winner)
        self.assertGreater(winner["supported_execution_load"], 0.0)
        self.assertEqual(winner["distinct_reentry_count"], 1)
        self.assertGreater(winner["reentry_support"], 0.0)
        self.assertLess(winner["reentry_support"], 1.0)
        self.assertGreater(result["diagnostics"]["qualified_context_count"], 1)
        for event in winner["events"]:
            self.assertLessEqual(event["supported_control_contribution"], event["own_control_load"])
            self.assertLessEqual(event["own_control_load"], event["anchor_intensity"])

    def test_bridge_growth_does_not_inflate_its_flank_intensity(self):
        events = [main_event(isolated_score(extract_rows(two_phrases(length)), fixed_main_context=True)) for length in (60, 108, 180, 230)]
        for event in events:
            self.assertAlmostEqual(event["anchor_intensity"], events[0]["anchor_intensity"], places=10)
            self.assertLessEqual(event["bounded_bridge_interaction"], event["anchor_intensity"])
            self.assertLessEqual(event["bounded_bridge_interaction"], event["bridge_intensity"])
        values = [event["bounded_bridge_interaction"] for event in events]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])), values)

    def test_either_weak_flank_forces_interaction_toward_zero(self):
        for side in ("left", "right"):
            values = []
            for scale in (1.0, .1, .01, .001):
                args = {f"{side}_scale": scale}
                event = main_event(isolated_score(extract_rows(two_phrases(200, **args)), fixed_main_context=True))
                values.append(event["bounded_bridge_interaction"])
                self.assertLessEqual(event["bounded_bridge_interaction"], 2*min(event["side_intensities"]))
            self.assertTrue(all(a > b for a, b in zip(values, values[1:])), (side, values))
            self.assertLess(values[-1], values[0]*.001)

    def test_rests_and_rate_discontinuity_weaken_same_beat_interaction(self):
        values = {}
        for interval in (25, 100, 500, 1500):
            rows = extract_rows(two_phrases(), intervals=[100]*3+[interval]+[100]*3)
            result = isolated_score(rows)
            values[interval] = result["winner"]["supported_execution_load"] if result["winner"] else 0.0
        self.assertGreater(values[100], values[25])
        self.assertGreater(values[100], values[500])
        self.assertGreater(values[500], values[1500])

    def test_globally_relaxed_deadlines_reduce_execution_not_relative_rhythm(self):
        fast = main_event(isolated_score(extract_rows(two_phrases(), interval=100), fixed_main_context=True))
        slow = main_event(isolated_score(extract_rows(two_phrases(), interval=200), fixed_main_context=True))
        self.assertAlmostEqual(fast["quality"], slow["quality"])
        self.assertLess(slow["bounded_bridge_interaction"], fast["bounded_bridge_interaction"])
        self.assertLess(slow["supported_control_contribution"], fast["supported_control_contribution"])

    def test_actual_slider_in_either_context_part_excludes_circle_reentry(self):
        for slider_at in (2, 4):
            with self.subTest(slider_at=slider_at):
                rows = actual_slider_rows(two_phrases(), slider_at)
                self.assertEqual(rows[slider_at]["ls.object_type"], "slider")
                self.assertIsNone(isolated_score(rows)["winner"])

    def test_ordinary_shape_changes_do_not_manufacture_reentry(self):
        cases = {
            "uniform_curve": curved_points(),
            "regular_variable_spacing": curved_points(distances=[20, 40, 20, 40, 20, 40, 20]),
            "square_jumps": curved_points(turn=math.pi/2),
            "straight_gap": [(60,190),(80,190),(100,190),(120,190),(320,190),(340,190),(360,190),(380,190)],
            "only_reversals": [(160 if index%2 else 240,190) for index in range(8)],
        }
        for name, points in cases.items():
            with self.subTest(name=name):
                self.assertIsNone(isolated_score(extract_rows(points))["winner"])

    def test_returning_to_an_old_position_does_not_erase_the_real_crossing(self):
        # Affection HDHR 154.797..155.271: two short curved phrases share a
        # coordinate, but the boundary still requires 150px within 95ms.
        points=[(0,303),(25,221),(109,200),(145,346),(60,366),(0,303)]
        result=isolated_score(extract_rows(points,intervals=[95,95,95,94,95],circle_size=5.2))
        self.assertIsNotNone(result['winner'])
        self.assertEqual(result['winner']['distinct_reentry_count'],1)
        self.assertGreater(result['winner']['supported_execution_load'],0.)

    def test_human_labeled_expanding_square_jumps_do_not_gain_reentry(self):
        # Altar NM 38.367..40.072, all circles. The real final slider head at
        # 40.186 is outside this excerpt; no object types were changed.
        points=[(167,156),(295,104),(347,232),(219,284),(201,58),(392,137),
                (311,330),(120,249),(326,24),(425,265),(182,364),(84,122),
                (443,116),(331,383),(62,269),(175,2)]
        intervals=[114,114,113,114,114,114,113,113,114,114,113,114,114,114,113]
        self.assertIsNone(isolated_score(extract_rows(points,intervals=intervals))['winner'])

    def test_two_real_flow_phrases_are_not_discarded_for_exact_bridge_reversal(self):
        points = [(60,190),(80,190),(100,190),(120,190),(400,190),(380,190),(360,190),(340,190)]
        winner = isolated_score(extract_rows(points))["winner"]
        self.assertIsNotNone(winner)
        self.assertGreater(winner["supported_execution_load"], 0.0)

    def test_repeated_context_views_are_not_repeated_events(self):
        evidence, records = scorer_inputs(extract_rows(two_phrases()))
        original = reentry.build_reentry_candidates(evidence, records, lambda *args: None)
        duplicated = copy.deepcopy(evidence)
        for event in duplicated["events"]:
            event["contexts"] *= 3
        repeated = reentry.build_reentry_candidates(duplicated, records, lambda *args: None)
        self.assertEqual(original["winner"]["distinct_reentry_count"], repeated["winner"]["distinct_reentry_count"])
        self.assertAlmostEqual(original["winner"]["value"], repeated["winner"]["value"], places=12)
        self.assertAlmostEqual(original["winner"]["reentry_support"], repeated["winner"]["reentry_support"], places=12)

    def test_rigid_transform_preserves_reentry_load(self):
        points = two_phrases()
        baseline = isolated_score(extract_rows(points))["winner"]
        for transformed in ([(x,384-y) for x,y in points], [(x+20,y+20) for x,y in points]):
            winner = isolated_score(extract_rows(transformed))["winner"]
            self.assertAlmostEqual(baseline["value"], winner["value"], places=10)

    def test_inputs_remain_immutable_and_public_numbers_are_finite(self):
        evidence, records = scorer_inputs(extract_rows(two_phrases()))
        before = copy.deepcopy((evidence, records))
        result = reentry.build_reentry_candidates(evidence, records, lambda *args: None)
        self.assertEqual(before, (evidence, records))
        json.dumps(result, allow_nan=False)

    def test_bridge_interaction_is_stable_bounded_symmetric_and_homogeneous(self):
        for anchor, bridge in ((1e-300,1e300), (1e300,1e-300), (1e300,1e300), (3,7), (0,7)):
            value = reentry.bridge_interaction(anchor, bridge)
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, min(anchor, bridge))
            self.assertEqual(value, reentry.bridge_interaction(bridge, anchor))
        self.assertAlmostEqual(reentry.bridge_interaction(6,14), 2*reentry.bridge_interaction(3,7))

    def test_repeated_switches_use_unique_bridges_and_exclude_them_from_all_flanks(self):
        result = isolated_score(extract_rows(three_phrases()))
        compound = [candidate for candidate in result["candidates"] if candidate["distinct_reentry_count"] > 1]
        self.assertTrue(compound)
        for candidate in compound:
            bridge_ids = candidate["bridge_transition_indices"]
            self.assertEqual(len(bridge_ids), len(set(bridge_ids)))
            self.assertEqual(len(bridge_ids), candidate["distinct_reentry_count"])
            self.assertTrue(set(bridge_ids).isdisjoint(candidate["anchor_transition_indices"]))
            self.assertEqual(len(candidate["anchor_transition_indices"]), len(set(candidate["anchor_transition_indices"])))
            self.assertLessEqual(candidate["reentry_event_evidence"], candidate["distinct_reentry_count"])
            self.assertLessEqual(candidate["reentry_support"], 1.0)

    def test_event_baselines_receive_their_own_bridge_and_stay_with_that_event(self):
        evidence, records = scorer_inputs(extract_rows(three_phrases()))
        called = set()
        def local_baseline(first, last, bridge):
            self.assertLessEqual(first, bridge)
            self.assertLessEqual(bridge, last)
            called.add((first, last, bridge))
            # Distinguishable local baselines expose accidental reuse of
            # another event's baseline, without invoking any map-level axis.
            return {"supported_execution_load": bridge/10000.0, "support": .1}
        result = reentry.build_reentry_candidates(evidence, records, local_baseline)
        self.assertTrue(called)
        for candidate in result["candidates"]:
            for event in candidate["events"]:
                self.assertEqual(event["local_baseline_load"], event["bridge_transition_index"]/10000.0)

    def test_supported_extra_load_is_not_suppressed_again_by_a_larger_baseline(self):
        evidence, records = scorer_inputs(extract_rows(two_phrases()))
        evidence["events"] = [event for event in evidence["events"] if event["bridge"]["from_source_row_index"] == 3]
        for event in evidence["events"]:
            event["contexts"] = [context for context in event["contexts"] if context["context_id"] == "L3R3"]
        # Hold physical event evidence and its already bounded/support-scaled
        # extra load fixed. Changing the callback's own local baseline must
        # not turn that marginal load into a second-order correction. This
        # documents the ADDITIVE_EXTRA_DIFFICULTY hypothesis, not a star label.
        candidates = []
        for base in (0.0, .1, 1.0, 10.0):
            result = reentry.build_reentry_candidates(
                evidence, records,
                lambda first, last, bridge, value=base: {"supported_execution_load": value, "support": .1},
            )
            candidate = result["winner"]
            candidates.append(candidate)
            self.assertAlmostEqual(candidate["local_baseline_load"], base, places=12)
        extra = candidates[0]["supported_extra_control_load"]
        self.assertGreater(extra, 0.0)
        for candidate in candidates[1:]:
            self.assertAlmostEqual(candidate["supported_extra_control_load"], extra, places=12)
            self.assertAlmostEqual(candidate["supported_execution_load"]-candidate["selected_baseline_load"], extra, places=12)
            self.assertEqual(candidate["bridge_transition_indices"], candidates[0]["bridge_transition_indices"])

    def test_additive_event_load_remains_bounded_by_its_own_anchor(self):
        evidence, records = scorer_inputs(extract_rows(three_phrases()))
        result = reentry.build_reentry_candidates(
            evidence, records,
            lambda first, last, bridge: {"supported_execution_load": bridge/10000.0, "support": .1},
        )
        for candidate in result["candidates"]:
            own_extra_upper_bound = max(event["anchor_intensity"] for event in candidate["events"])
            self.assertLessEqual(candidate["supported_execution_load"], candidate["selected_baseline_load"]+own_extra_upper_bound)
            self.assertGreaterEqual(candidate["local_reentry_load_increment"], 0.0)
            self.assertAlmostEqual(candidate["supported_extra_control_load"], math.fsum(event["supported_control_contribution"] for event in candidate["events"]), places=12)
            for event in candidate["events"]:
                self.assertLessEqual(event["supported_control_contribution"], event["own_control_load"])
                self.assertLessEqual(event["own_control_load"], event["anchor_intensity"])


class CompoundFlowLayerSupportTests(unittest.TestCase):
    def test_equal_intensity_reduces_to_its_own_bounded_support(self):
        result = reentry.intensity_layer_support([{"intensity":2.0,"quality":.8} for _ in range(8)])
        expected = 2.0*-math.expm1(-((8*.8/reentry.FLOW_LINK_SUPPORT_REFERENCE)**2))
        self.assertAlmostEqual(result["supported_load"], expected, places=12)
        self.assertEqual(len(result["layers"]), 1)

    def test_variable_intensity_retains_the_higher_part(self):
        constant = reentry.intensity_layer_support([{"intensity":1.0,"quality":1.0} for _ in range(8)])
        variable = reentry.intensity_layer_support([{"intensity":float(1+index%2),"quality":1.0} for index in range(8)])
        self.assertGreater(variable["supported_load"], constant["supported_load"])

    def test_cheap_links_cannot_establish_two_high_weak_links(self):
        high_layers = []
        for count in (2,8,16):
            links = [{"intensity":100.0,"quality":.02}]*2 + [{"intensity":1.0,"quality":1.0}]*count
            result = reentry.intensity_layer_support(links)
            high = result["layers"][-1]
            self.assertEqual(high["level"], 100.0)
            self.assertAlmostEqual(high["evidence"], .04)
            high_layers.append(high)
        for high in high_layers[1:]:
            self.assertEqual(high, high_layers[0])

    def test_a_single_peak_is_not_supported_at_its_outlier_intensity(self):
        ordinary = reentry.intensity_layer_support([{"intensity":1.0,"quality":1.0}]*9)
        one_peak = reentry.intensity_layer_support([{"intensity":1.0,"quality":1.0}]*8+[{"intensity":100.0,"quality":1.0}])
        self.assertAlmostEqual(ordinary["supported_load"], one_peak["supported_load"])
        self.assertEqual(one_peak["isolated_peak_cap"], 1.0)
        self.assertEqual(max(link["intensity"] for link in one_peak["links"]), 100.0)

    def test_extra_retains_single_event_with_its_own_finite_support(self):
        item = {"intensity":3.0,"quality":.8}
        extra = reentry.intensity_layer_support([item], support_reference=2.0, retain_single=True)
        anchor = reentry.intensity_layer_support([item])
        self.assertGreater(extra["supported_load"], 0.0)
        self.assertLess(extra["supported_load"], 3.0)
        self.assertEqual(anchor["supported_load"], 0.0)
        self.assertAlmostEqual(extra["supported_load"], 3.0*-math.expm1(-((.8/2.0)**2)), places=12)

    def test_extra_high_layer_cannot_borrow_cheap_event_support(self):
        high_layers = []
        for count in (2,8,16):
            entries = [{"intensity":100.0,"quality":.02}]*2+[{"intensity":1.0,"quality":1.0}]*count
            result = reentry.intensity_layer_support(entries, support_reference=2.0, retain_single=True)
            high = result["layers"][-1]
            self.assertAlmostEqual(high["evidence"], .04)
            high_layers.append(high)
            self.assertAlmostEqual(result["supported_load"], math.fsum(item["supported_load_contribution"] for item in result["links"]), places=12)
            for item in result["links"]:
                self.assertGreaterEqual(item["supported_load_contribution"], 0.0)
                self.assertLessEqual(item["supported_load_contribution"], item["capped_intensity"])
        for high in high_layers[1:]:
            self.assertEqual(high, high_layers[0])

    def test_common_activation_scales_load_linearly_without_changing_link_evidence(self):
        inputs = [{"intensity":float(1+index%2),"quality":.8} for index in range(8)]
        baseline = reentry.intensity_layer_support(inputs)
        for activation in (0.0,.01,.25,1.0):
            result = reentry.intensity_layer_support([{**item,"activation":activation} for item in inputs])
            self.assertAlmostEqual(result["link_evidence"], baseline["link_evidence"], places=12)
            self.assertAlmostEqual(result["support"], baseline["support"], places=12)
            self.assertAlmostEqual(result["supported_load"], activation*baseline["supported_load"], places=12)
            self.assertAlmostEqual(result["supported_load"], math.fsum(item["supported_load_contribution"] for item in result["links"]), places=12)
            for item in result["links"]:
                self.assertLessEqual(item["supported_load_contribution"], item["capped_intensity"]*activation+1e-12)

    def test_added_weak_activation_neither_dilutes_nor_establishes_high_activation(self):
        established = [{"intensity":1.0,"quality":1.0,"activation":1.0}]*4
        baseline = reentry.intensity_layer_support(established)
        high_bands = []
        for count in (2,8,16):
            result = reentry.intensity_layer_support(established+[{"intensity":1.0,"quality":1.0,"activation":.01}]*count)
            self.assertGreaterEqual(result["supported_load"], baseline["supported_load"])
            high_band = result["layers"][0]["activation_layers"][-1]
            self.assertEqual(high_band["level"], 1.0)
            self.assertEqual(high_band["evidence"], 4.0)
            high_bands.append(high_band)
            for item in result["links"]:
                self.assertLessEqual(item["supported_load_contribution"], item["capped_intensity"]*item["activation"]+1e-12)
        self.assertTrue(all(band == high_bands[0] for band in high_bands[1:]))
        inactive = reentry.intensity_layer_support(established+[{"intensity":1.0,"quality":1.0,"activation":0.0}]*8)
        self.assertAlmostEqual(inactive["supported_load"], baseline["supported_load"], places=12)

    def test_tiny_activation_cannot_unlock_a_different_isolated_intensity_peak(self):
        original = [{"intensity":100.0,"quality":1.0,"activation":1.0}]+[{"intensity":1.0,"quality":1.0,"activation":1.0}]*2
        baseline = reentry.intensity_layer_support(original)["supported_load"]
        gains = []
        for activation in (.1,.01,.0001,.000001,0.0):
            result = reentry.intensity_layer_support(original+[{"intensity":200.0,"quality":1.0,"activation":activation}])
            gain = result["supported_load"]-baseline
            gains.append(gain)
            self.assertGreaterEqual(gain, -1e-12)
            self.assertLessEqual(gain, 200*activation+1e-12)
        self.assertTrue(all(a >= b-1e-12 for a,b in zip(gains,gains[1:])), gains)
        self.assertAlmostEqual(gains[-1], 0.0, places=12)

    def test_tiny_quality_cannot_unlock_a_different_isolated_intensity_peak(self):
        original = [{"intensity":100.0,"quality":1.0,"activation":1.0}]+[{"intensity":1.0,"quality":1.0,"activation":1.0}]*2
        baseline = reentry.intensity_layer_support(original)["supported_load"]
        gains = []
        for quality in (.1,.01,.0001,.000001,0.0):
            result = reentry.intensity_layer_support(original+[{"intensity":200.0,"quality":quality,"activation":1.0}])
            gain = result["supported_load"]-baseline
            gains.append(gain)
            self.assertGreaterEqual(gain, -1e-12)
            self.assertLessEqual(gain, 200*quality+1e-12)
        self.assertTrue(all(a >= b-1e-12 for a,b in zip(gains,gains[1:])), gains)
        self.assertAlmostEqual(gains[-1], 0.0, places=12)

    def test_adding_a_tiny_quality_low_extra_does_not_collapse_a_valid_single_event(self):
        original = [{"intensity":100.0,"quality":1.0}]
        baseline = reentry.intensity_layer_support(original, support_reference=2.0, retain_single=True)["supported_load"]
        self.assertGreater(baseline, 0.0)
        for quality in (.1,.01,.0001,.000001,0.0):
            result = reentry.intensity_layer_support(original+[{"intensity":1.0,"quality":quality}], support_reference=2.0, retain_single=True)
            self.assertGreaterEqual(result["supported_load"], baseline-1e-12)
            self.assertLessEqual(result["supported_load"]-baseline, quality+1e-12)

    def test_bridge_spacing_changes_activation_not_fixed_context_flank_quality(self):
        bases = []
        for length in (60,108,180,230):
            evidence, records = scorer_inputs(extract_rows(two_phrases(length)))
            events = reentry._context_options(evidence, records, 4000, 32)
            event = next(event for event in events if event["bridge_index"] == 3)
            option = next(option for option in event["options"] if option["context"]["context_id"] == "L3R3")
            bases.append(reentry.compound_flow_base([option], records))
        for result in bases[1:]:
            self.assertAlmostEqual(result["link_evidence"], bases[0]["link_evidence"], places=10)
            self.assertAlmostEqual(result["support"], bases[0]["support"], places=10)
            for first, second in zip(bases[0]["links"], result["links"]):
                self.assertEqual(first["from_transition_index"], second["from_transition_index"])
                self.assertEqual(first["to_transition_index"], second["to_transition_index"])
                self.assertAlmostEqual(first["quality"], second["quality"], places=10)
                self.assertAlmostEqual(first["intensity"], second["intensity"], places=10)
        activations = [result["links"][0]["activation"] for result in bases]
        self.assertTrue(all(first < second for first,second in zip(activations,activations[1:])), activations)

    def test_real_weak_high_flank_is_unique_and_does_not_include_either_bridge(self):
        evidence, records = scorer_inputs(extract_rows(weak_high_flank_between_cheap_phrases(), interval=50))
        events = reentry._context_options(evidence, records, 4000, 32)
        selected = []
        for event in events:
            if event["bridge_index"] in (4,8):
                context = "L4R3" if event["bridge_index"] == 4 else "L3R4"
                selected.append(next(option for option in event["options"] if option["context"]["context_id"] == context))
        self.assertEqual(len(selected), 2)
        combined = reentry.compound_flow_base(selected, records)
        self.assertEqual(combined["unique_link_count"], 8)
        link_keys = [(link["from_transition_index"],link["to_transition_index"]) for link in combined["links"]]
        self.assertEqual(len(link_keys), len(set(link_keys)))
        self.assertTrue(all(4 not in key and 8 not in key for key in link_keys))
        high_links = [link for link in combined["links"] if link["intensity"] > 1.0]
        self.assertEqual(len(high_links), 2)
        for link in high_links:
            self.assertLessEqual(link["quality"], math.cos(math.radians(89))+1e-12)
        high_band = [layer for layer in combined["layers"] if layer["level"] > 1.0]
        self.assertTrue(high_band)
        self.assertTrue(all(layer["evidence"] <= sum(link["quality"] for link in high_links)+1e-12 for layer in high_band))
        repeated = reentry.compound_flow_base(selected+selected, records)
        self.assertEqual(combined, repeated)
        individual = [reentry.compound_flow_base([option], records) for option in selected]
        for link in high_links:
            key = (link["from_transition_index"],link["to_transition_index"])
            views = [other for result in individual for other in result["links"] if (other["from_transition_index"],other["to_transition_index"]) == key]
            qualities = [other["quality"] for other in views]
            self.assertTrue(all(math.isclose(quality, qualities[0],abs_tol=1e-12) for quality in qualities))
            self.assertEqual(link["quality"], max(qualities))
            self.assertEqual(link["activation"], max(other["activation"] for other in views))

    def test_span_rest_between_event_contexts_cannot_establish_compound_flow(self):
        points = separated_events_with_middle_motion()
        selected_results = []
        for middle_interval in (50.0,500.0):
            intervals = [50.0]*(len(points)-1)
            intervals[8] = middle_interval
            evidence, records = scorer_inputs(extract_rows(points, intervals=intervals))
            evidence["events"] = [event for event in evidence["events"] if event["bridge_transition_index"] in (3,13)]
            self.assertEqual(len(evidence["events"]), 2)
            for event in evidence["events"]:
                event["contexts"] = [context for context in event["contexts"] if context["context_id"] == "L3R3"]
                self.assertEqual(len(event["contexts"]), 1)
                self.assertEqual(event["contexts"][0]["timing"]["continuity_evidence"], 1.0)
            result = reentry.build_reentry_candidates(evidence, records, lambda *args: None)
            selected_results.append(result)
        continuous, rested = selected_results
        compounds = [candidate for candidate in continuous["candidates"] if candidate["distinct_reentry_count"] == 2]
        self.assertTrue(compounds)
        self.assertTrue(all(candidate["span_timing_continuity"] == 1.0 for candidate in compounds))
        # Either the weak compound candidate loses to its individual events,
        # or its full-span support explicitly records the missed middle rest.
        for candidate in rested["candidates"]:
            if candidate["distinct_reentry_count"] == 2:
                self.assertLess(candidate["span_timing_continuity"], .01)
                self.assertLess(candidate["compound_baseline_load"], max(item["compound_baseline_load"] for item in compounds))


class FlowReentryPublicIntegrationTests(unittest.TestCase):
    def test_public_extraction_handles_the_nineteen_controlled_cases(self):
        cases = {
            "short_reentry": extract_rows(two_phrases()),
            "bridge_60": extract_rows(two_phrases(60)),
            "bridge_180": extract_rows(two_phrases(180)),
            "bridge_230": extract_rows(two_phrases(230)),
            "rest_500": extract_rows(two_phrases(), intervals=[100]*3+[500]+[100]*3),
            "rest_1500": extract_rows(two_phrases(), intervals=[100]*3+[1500]+[100]*3),
            "quarter_interval": extract_rows(two_phrases(), intervals=[100]*3+[25]+[100]*3),
            "all_deadlines_doubled": extract_rows(two_phrases(), interval=200),
            "slider_at_destination": actual_slider_rows(two_phrases(), 4),
            "slider_in_left_flank": actual_slider_rows(two_phrases(), 2),
            "uniform_curve": extract_rows(curved_points()),
            "variable_spacing": extract_rows(curved_points(distances=[20,40,20,40,20,40,20])),
            "square_jumps": extract_rows(curved_points(turn=math.pi/2)),
            "straight_gap": extract_rows([(60,190),(80,190),(100,190),(120,190),(320,190),(340,190),(360,190),(380,190)]),
            "reentry_reversal": extract_rows([(60,190),(80,190),(100,190),(120,190),(400,190),(380,190),(360,190),(340,190)]),
            "only_reversals": extract_rows([(160 if index%2 else 240,190) for index in range(8)]),
            "tiny_flanks": extract_rows(two_phrases(200,.01,.01)),
            "mirror": extract_rows([(x,384-y) for x,y in two_phrases()]),
            "translate": extract_rows([(x+20,y+20) for x,y in two_phrases()]),
        }
        self.assertEqual(len(cases), 19)
        results = {}
        for name, rows in cases.items():
            with self.subTest(name=name):
                result = flow.extract_flow_measure(rows, circle_size=4)
                results[name] = result
                self.assertEqual(result["status"], "FULL")
                self.assertEqual(result["coverage"], 1.0)
                json.dumps(result, allow_nan=False)
                self.assertFalse(result["signals"]["spatial_reentry"]["continuous_and_reentry_candidates_are_summed"])
        for name in ("slider_at_destination", "slider_in_left_flank", "uniform_curve", "variable_spacing", "square_jumps", "straight_gap", "only_reversals"):
            self.assertIsNone(results[name]["signals"]["spatial_reentry"]["best_candidate"], name)
        for name in ("short_reentry", "bridge_60", "bridge_180", "bridge_230", "reentry_reversal"):
            candidate = results[name]["signals"]["spatial_reentry"]["best_candidate"]
            self.assertIsNotNone(candidate, name)
            self.assertGreater(candidate["local_reentry_load_increment"], 0.0, name)
        baseline = results["short_reentry"]
        for name in ("mirror", "translate"):
            self.assertAlmostEqual(results[name]["value"], baseline["value"], places=10)
        self.assertLess(results["all_deadlines_doubled"]["value"], baseline["value"])
        self.assertLess(results["tiny_flanks"]["value"], baseline["value"])

    def test_distant_hard_flow_cannot_supply_the_reentry_baseline(self):
        from test_flow_execution_v02 import orbit
        local_points = two_phrases()
        local = flow.extract_flow_measure(extract_rows(local_points), circle_size=4)
        hard_points = orbit(32, distance=100.0, turn=math.pi/3)
        joined = flow.extract_flow_measure(
            extract_rows(hard_points+local_points, intervals=[55.0]*32+[5000.0]+[100.0]*7), circle_size=4
        )
        a = local["signals"]["spatial_reentry"]["best_candidate"]
        b = joined["signals"]["spatial_reentry"]["best_candidate"]
        self.assertGreater(joined["value"], local["value"])
        self.assertAlmostEqual(a["local_baseline_load"], b["local_baseline_load"], places=10)
        self.assertAlmostEqual(a["value"], b["value"], places=10)

    def test_repeated_distant_pattern_does_not_sum_or_share_reentry_support(self):
        points = two_phrases()
        once = flow.extract_flow_measure(extract_rows(points), circle_size=4)
        twice = flow.extract_flow_measure(extract_rows(points+points, intervals=[100]*7+[5000]+[100]*7), circle_size=4)
        self.assertAlmostEqual(once["value"], twice["value"], places=10)
        a = once["signals"]["spatial_reentry"]["best_candidate"]
        b = twice["signals"]["spatial_reentry"]["best_candidate"]
        self.assertAlmostEqual(a["reentry_support"], b["reentry_support"], places=10)
        self.assertEqual(a["distinct_reentry_count"], b["distinct_reentry_count"])

    def test_mod_labels_do_not_reapply_transformed_circle_geometry(self):
        rows = extract_rows(two_phrases(), circle_size=5.2)
        baseline = flow.extract_flow_measure(rows, circle_size=5.2)
        for mods in (("HD",), ("HR",), ("HD","HR"), ("HD","DT")):
            result = flow.extract_flow_measure(rows, effective_mods=mods, circle_size=5.2)
            self.assertAlmostEqual(baseline["value"], result["value"], places=12)
            self.assertAlmostEqual(
                baseline["signals"]["spatial_reentry"]["best_candidate"]["value"],
                result["signals"]["spatial_reentry"]["best_candidate"]["value"], places=12
            )


if __name__ == "__main__":
    unittest.main()

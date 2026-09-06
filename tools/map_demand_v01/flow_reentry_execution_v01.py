"""Local circle-phrase reentry load; an explicitly uncalibrated hypothesis.

Alternative views of one bridge are never repetitions. A bridge cannot also
be a supporting phrase movement in the same candidate. Compound Flow uses
unique internal phrase links, with support supplied at each intensity level
by links that actually reach that level. Local bounded interactions provide
the extra reentry load; no whole-map axis supplies either contribution.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Callable, Mapping

from . import flow_target_size_v01 as scale

SCHEMA_VERSION = "flow_reentry_execution_v0.2.0"
REENTRY_SUPPORT_REFERENCE = 2.0
FLOW_LINK_SUPPORT_REFERENCE = 4.0
NUMERIC_EPSILON = 1e-12


def _harmonic(first: float, second: float) -> float:
    if first <= 0.0 or second <= 0.0:
        return 0.0
    lo, hi = sorted((first, second))
    return lo * (2.0 / (1.0 + lo / hi))


def bridge_interaction(anchor: float, bridge: float) -> float:
    """A*I/(A+I), stable and bounded by BOTH local inputs."""
    if anchor <= 0.0 or bridge <= 0.0:
        return 0.0
    lo, hi = sorted((anchor, bridge))
    return lo / (1.0 + lo / hi)


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total = math.fsum(weights)
    return math.fsum(value * (weight / total) for value, weight in zip(values, weights)) if total > 0.0 else 0.0


def _established_weights(weights: list[float], retain_single: bool) -> list[float]:
    """One link cannot outweigh all corroborating links in this layer."""
    result = list(weights)
    if result and not retain_single:
        strongest = max(range(len(result)), key=result.__getitem__)
        others = math.fsum(weight for index, weight in enumerate(result) if index != strongest)
        result[strongest] = min(result[strongest], others)
    return result


def intensity_layer_support(
    links: list[dict[str, Any]], *,
    support_reference: float = FLOW_LINK_SUPPORT_REFERENCE, retain_single: bool = False,
) -> dict[str, Any]:
    """Integrate supported intensity; cheap links cannot support a high layer.

    Equal-intensity, equal-activation links reduce exactly to
    I * activation * (1-exp(-(established_mass/reference)^2)). This mass is
    sum(q) when no one link outweighs all others (or single events are allowed).
    Activation has its own
    integration layers: weak activation cannot dilute stronger activation,
    nor lend all its evidence to that stronger geometry level.
    All inputs are already local, unique links; raw intensity and provenance
    remain visible even when the one isolated maximum is capped.
    """
    if any(not math.isfinite(link["intensity"]) or link["intensity"] < 0.0 or not 0.0 <= link["quality"] <= 1.0 or not 0.0 <= link.get("activation", 1.0) <= 1.0 for link in links):
        raise ValueError("Invalid compound Flow link")
    usable = [dict(link) for link in links if link["intensity"] > 0.0 and link["quality"] > 0.0]
    if not math.isfinite(support_reference) or support_reference <= 0.0:
        raise ValueError("Invalid intensity support reference")
    # Single reentries are valid and retain their own finite support. An
    # event-level second-peak cap would abruptly reduce such an event when
    # an arbitrarily weak additional event appears. Layer support already
    # prevents it borrowing lower-intensity evidence.
    cap = max((link["intensity"] for link in usable), default=0.0) if retain_single else (sorted(link["intensity"] for link in usable)[-2] if len(usable) > 1 else 0.0)
    for link in usable:
        link["capped_intensity"] = min(link["intensity"], cap)
        link["activation"] = link.get("activation", 1.0)
        link["supported_load_contribution"] = 0.0
    mass = math.fsum(link["quality"] for link in usable)
    established_mass = math.fsum(_established_weights([link["quality"] for link in usable], retain_single))
    layers = []
    previous = 0.0
    for level in sorted({link["capped_intensity"] for link in usable if link["capped_intensity"] > 0.0}):
        owners = [link for link in usable if link["capped_intensity"] >= level]
        evidence = math.fsum(link["quality"] for link in owners)
        established_evidence = math.fsum(_established_weights([link["quality"] for link in owners], retain_single))
        support = -math.expm1(-((established_evidence / support_reference) ** 2))
        activation_layers = []
        previous_activation = 0.0
        for activation in sorted({link["activation"] for link in owners}):
            activation_owners = [link for link in owners if link["activation"] >= activation]
            activation_evidence = math.fsum(link["quality"] for link in activation_owners)
            # Establish a layer with continuously weighted corroboration.
            # One q=1 link plus one q=epsilon link has only 2*epsilon mass;
            # an infinitesimal second source cannot unlock an isolated peak.
            owner_weights = _established_weights([link["quality"] for link in activation_owners], retain_single)
            established_activation_evidence = math.fsum(owner_weights)
            activation_support = -math.expm1(-((established_activation_evidence / support_reference) ** 2))
            activated_support_increment = (activation - previous_activation) * activation_support
            increment = (level - previous) * activated_support_increment
            for link, weight in zip(activation_owners, owner_weights):
                link["supported_load_contribution"] += increment * (weight / established_activation_evidence) if established_activation_evidence > 0.0 else 0.0
            activation_layers.append({
                "level": activation, "delta": activation - previous_activation,
                "evidence": activation_evidence, "support": activation_support,
                "established_evidence": established_activation_evidence,
                "activated_support_increment": activated_support_increment, "load_increment": increment,
            })
            previous_activation = activation
        activated_support = math.fsum(item["activated_support_increment"] for item in activation_layers)
        layers.append({
            "level": level, "delta": level - previous, "evidence": evidence,
            "established_evidence": established_evidence, "support": support,
            "activated_support": activated_support, "activation_layers": activation_layers,
            "load_increment": (level - previous) * activated_support,
        })
        previous = level
    return {
        "supported_load": math.fsum(layer["load_increment"] for layer in layers),
        "link_evidence": mass,
        "established_link_evidence": established_mass,
        "support": -math.expm1(-((established_mass / support_reference) ** 2)),
        "support_reference": support_reference, "retain_single": retain_single,
        "evidence_policy": "SINGLE_EVENT_ALLOWED" if retain_single else "DOMINANT_LINK_MASS_BOUNDED_BY_OTHER_LINKS",
        "isolated_peak_cap": cap, "links": usable, "layers": layers,
    }


def compound_flow_base(selected: list[dict[str, Any]], records: Mapping[int, dict[str, Any]], span_timing: float = 1.0) -> dict[str, Any]:
    """Own phrase links only; link evidence is independent of bridge geometry."""
    links = {}
    bridges = {option["bridge_index"] for option in selected}
    for option in selected:
        context = option["context"]
        activation = option["switch_ratio"]
        for side in (context["left"], context["right"]):
            indices = side["transition_indices"]
            for first, second, rotation in zip(indices, indices[1:], side["internal_rotations"]):
                if first in bridges or second in bridges:
                    continue
                relative_time = math.log(records[first]["time_ms"]) - math.log(records[second]["time_ms"])
                quality = min(1.0, max(0.0, rotation[0]) * math.exp(-(relative_time ** 2)) * span_timing)
                key = (first, second)
                if quality <= NUMERIC_EPSILON:
                    continue
                intensity = _harmonic(records[first]["intensity"], records[second]["intensity"])
                existing = links.get(key)
                if existing is None or activation > existing["activation"]:
                    links[key] = {
                        "from_transition_index": first, "to_transition_index": second,
                        "intensity": intensity, "quality": quality, "activation": activation,
                        "activation_source_event_id": option["event_id"],
                        "activation_source_context_id": context["context_id"],
                    }
    result = intensity_layer_support([links[key] for key in sorted(links)])
    result.update({
        "unique_link_count": len(links), "span_timing_continuity": span_timing,
        "support_reference_links": FLOW_LINK_SUPPORT_REFERENCE,
        "overlap_quality_policy": "IDENTICAL_OWN_LINK_EVIDENCE_NOT_SUM",
        "overlap_activation_policy": "MAX_OWN_CONTEXT_NOT_SUM", "bridge_links_excluded": True,
        "intensity_source": "HARMONIC_ADJACENT_RAW_MOVEMENT_INTENSITY",
        "support_policy": "JOINT_INTENSITY_AND_ACTIVATION_LAYER_INTEGRAL",
        "isolated_peak_policy": "SECOND_INTENSITY_AND_CONTINUOUS_CORROBORATION_PER_JOINT_LAYER",
    })
    return result


def _context_options(evidence: Mapping[str, Any], records: Mapping[int, dict[str, Any]], max_span_ms: float, max_movements: int) -> list[dict[str, Any]]:
    events = []
    for event in evidence["events"]:
        bridge_index = event["bridge_transition_index"]
        bridge = records.get(bridge_index)
        if bridge is None:
            continue
        options = []
        for context in event["contexts"]:
            lo, hi = context["transition_index_first"], context["transition_index_last"]
            indices = [*context["left"]["transition_indices"], *context["right"]["transition_indices"]]
            if context["end_ms"] - context["start_ms"] > max_span_ms or hi - lo + 1 > max_movements:
                continue
            if any(index not in records for index in range(lo, hi + 1)):
                continue
            gap = context["spatial"]["boundary_step_excess_ratio"]
            # A changed average direction alone also occurs on an ordinary
            # uninterrupted circular arc. Require an enlarged actual boundary
            # step AND a change at the junction relative to its own phrases.
            # The full phrase footprints may overlap after the crossing.
            change = max(context["direction"]["rotation_change_at_boundary"])
            if gap <= NUMERIC_EPSILON or change <= NUMERIC_EPSILON:
                continue
            quality = _harmonic(context["left"]["soft_alignment"], context["right"]["soft_alignment"])
            timing = context["timing"]
            quality *= timing["continuity_evidence"] * timing["bridge_timing_match_evidence"]
            if quality <= NUMERIC_EPSILON:
                continue
            # Median is local and bridge-free. Two very short side movements
            # can prove only their shared intensity, hence use their minimum.
            sides = []
            for side in (context["left"], context["right"]):
                values = [records[index]["intensity"] for index in side["transition_indices"]]
                sides.append(min(values) if len(values) == 2 else statistics.median(values))
            anchor = _harmonic(*sides)
            interaction = bridge_interaction(anchor, bridge["intensity"])
            switch = math.sqrt(gap * change)
            control = interaction * switch
            if control <= 0.0:
                continue
            options.append({
                "event_id": event["event_id"], "bridge_index": bridge_index,
                "circle_run_id": event["circle_run_id"], "context": context,
                "anchor_indices": frozenset(indices),
                "quality": quality, "side_intensities": sides,
                "anchor_intensity": anchor, "bridge_intensity": bridge["intensity"],
                "bounded_bridge_interaction": interaction,
                "switch_ratio": switch, "control_load": control,
            })
        if options:
            events.append({"bridge_index": bridge_index, "circle_run_id": event["circle_run_id"], "options": options})
    return events


def build_reentry_candidates(
    evidence: Mapping[str, Any], records: Mapping[int, dict[str, Any]],
    local_baseline: Callable[[int, int, int], dict[str, Any] | None], *,
    max_span_ms: float = 4000.0, max_movements: int = 32,
) -> dict[str, Any]:
    """Return bounded local candidates and bridge-unique diagnostic events.

    Each ending context extends backwards through compatible bridge events.
    At an earlier bridge its strongest compatible local-control context is
    selected. All intermediate group lengths can compete. This deterministic
    local selection is not a claim of exhaustive segmentation optimisation.
    """
    events = _context_options(evidence, records, max_span_ms, max_movements)
    candidates = []
    baseline_cache = {}
    evaluated_count = 0

    def baseline(option):
        context = option["context"]
        key = (context["transition_index_first"], context["transition_index_last"], option["bridge_index"])
        if key not in baseline_cache:
            baseline_cache[key] = local_baseline(*key)
        return baseline_cache[key]

    def score(selected):
        lo = min(option["context"]["transition_index_first"] for option in selected)
        hi = max(option["context"]["transition_index_last"] for option in selected)
        window = [records[index] for index in range(lo, hi + 1)]
        # Event-local cadence does not see a rest BETWEEN disjoint contexts.
        # The weakest adjacent relative interval match spans the whole group.
        interval_logs = [math.log(record["time_ms"]) for record in window]
        span_timing = min((math.exp(-((second - first) ** 2)) for first, second in zip(interval_logs, interval_logs[1:])), default=1.0)
        weights = [option["quality"] * span_timing for option in selected]
        raw_controls = [option["control_load"] for option in selected]
        control_support = intensity_layer_support([
            {"intensity": value, "quality": weight, "event_id": option["event_id"]}
            for option, value, weight in zip(selected, raw_controls, weights)
        ], support_reference=REENTRY_SUPPORT_REFERENCE, retain_single=True)
        mass, support = control_support["link_evidence"], control_support["support"]
        cap = control_support["isolated_peak_cap"]
        contributions = {item["event_id"]: item["supported_load_contribution"] for item in control_support["links"]}
        own_bases = [(baseline(option) or {}).get("supported_execution_load", 0.0) for option in selected]
        own_base = _weighted_mean(own_bases, weights)
        compound = compound_flow_base(selected, records, span_timing)
        selected_base = max(own_base, compound["supported_load"])
        # ``control`` is a bounded EXTRA difficulty load, not a perpendicular
        # physical vector. Both terms retain their own source and support.
        extra = control_support["supported_load"]
        load = selected_base + extra
        if not math.isfinite(load):
            raise ValueError("Nonfinite spatial reentry load")
        log_load = math.log1p(scale.FLOW_LOG_GAIN * load) if load <= 1.0 else math.log(load) + math.log(scale.FLOW_LOG_GAIN) + math.log1p((1.0 / load) / scale.FLOW_LOG_GAIN)
        used_sources = sorted({index for option in selected for index in option["anchor_indices"]})
        best_base_support = max((baseline(option) or {}).get("support", 0.0) for option in selected)
        return {
            "kind": "CIRCLE_SPATIAL_REENTRY", "value": scale.FLOW_LOG_COEFFICIENT * log_load / math.log(2.0),
            "support": max(best_base_support, support, compound["support"]), "chain_support": best_base_support,
            "reentry_support": support, "reentry_event_evidence": mass,
            "supported_execution_load": load, "execution_intensity": None,
            "raw_peak_intensity": max(record["intensity"] for record in window),
            "movement_execution_intensity": None,
            "local_baseline_load": own_base, "compound_flow_base": compound,
            "compound_baseline_load": compound["supported_load"], "selected_baseline_load": selected_base,
            "compound_baseline_growth": max(0.0, selected_base - own_base),
            "supported_extra_control_load": extra, "reentry_control_support": control_support,
            "span_timing_continuity": span_timing,
            "local_reentry_load_increment": max(0.0, load - own_base),
            "control_load_before_support": _weighted_mean([min(value, cap) for value in raw_controls], weights),
            "raw_peak_reentry_control_load": max(raw_controls),
            "start_ms": window[0]["start_time_ms"], "end_ms": window[-1]["time"],
            "duration_ms": window[-1]["time"] - window[0]["start_time_ms"],
            "event_count": len(window), "distinct_reentry_count": len(selected),
            "source_index_first": window[0]["source_index"] - 1,
            "source_index_last": window[-1]["source_index"],
            "block": window[0]["block"], "segment": window[0]["segment"],
            "run": window[0]["run"], "circle_run_id": selected[0]["circle_run_id"],
            "anchor_transition_indices": used_sources,
            "bridge_transition_indices": sorted(option["bridge_index"] for option in selected),
            "mean_distance_px": statistics.fmean(record["distance"] for record in window),
            "mean_time_ms": statistics.fmean(record["time_ms"] for record in window),
            "mean_velocity_px_per_ms": statistics.fmean(record["distance"] / record["time_ms"] for record in window),
            "mean_radius_px": statistics.fmean(record["radius"] for record in window),
            "slider_tangent_unknown_count": 0, "control_source_within_candidate": True,
            "spatial_reentry_classified": True,
            "events": [{
                "event_id": option["event_id"], "bridge_transition_index": option["bridge_index"],
                "context_id": option["context"]["context_id"], "context": option["context"],
                "quality": option["quality"], "effective_quality": option["quality"] * span_timing,
                "side_intensities": option["side_intensities"],
                "anchor_intensity": option["anchor_intensity"], "bridge_intensity": option["bridge_intensity"],
                "bounded_bridge_interaction": option["bounded_bridge_interaction"],
                "switch_ratio": option["switch_ratio"], "local_baseline_load": base,
                "own_control_load": raw, "supported_control_contribution": contributions.get(option["event_id"], 0.0),
            } for option, base, raw in zip(selected, own_bases, raw_controls)],
        }

    for end_index, event in enumerate(events):
        best_at_event = None

        def consider(selected):
            nonlocal best_at_event, evaluated_count
            candidate = score(selected)
            evaluated_count += 1
            rank = lambda value: (value["value"], value["support"], -value["duration_ms"])
            if best_at_event is None or rank(candidate) > rank(best_at_event):
                best_at_event = candidate

        for ending in event["options"]:
            selected = [ending]
            consider(selected)
            for prior_index in range(end_index - 1, -1, -1):
                prior = events[prior_index]
                if prior["circle_run_id"] != event["circle_run_id"]:
                    break
                if event["bridge_index"] - prior["bridge_index"] >= max_movements:
                    break
                if records[event["bridge_index"]]["time"] - records[prior["bridge_index"]]["time"] > max_span_ms:
                    break
                valid = []
                for option in prior["options"]:
                    if any(option["bridge_index"] in other["anchor_indices"] or other["bridge_index"] in option["anchor_indices"] for other in selected):
                        continue
                    lo = min(option["context"]["transition_index_first"], *(other["context"]["transition_index_first"] for other in selected))
                    hi = max(option["context"]["transition_index_last"], *(other["context"]["transition_index_last"] for other in selected))
                    if hi - lo + 1 > max_movements or records[hi]["time"] - records[lo]["start_time_ms"] > max_span_ms:
                        continue
                    if any(index not in records for index in range(lo, hi + 1)):
                        continue
                    valid.append(option)
                if not valid:
                    continue
                selected.append(max(valid, key=lambda item: (item["control_load"] * item["quality"], -item["context"]["circle_count"])))
                consider(selected)
        if best_at_event is not None:
            candidates.append(best_at_event)
    winner = max(candidates, key=lambda item: (item["value"], item["support"], -item["duration_ms"])) if candidates else None
    return {
        "candidates": candidates, "winner": winner,
        "diagnostics": {
            "schema_version": SCHEMA_VERSION,
            "classified_bridge_count": len(events),
            "qualified_context_count": sum(len(event["options"]) for event in events),
            "candidate_count": evaluated_count,
            "retained_best_per_bridge_count": len(candidates),
            "reentry_support_reference": REENTRY_SUPPORT_REFERENCE,
            "single_event_may_have_bounded_support": True,
            "bridge_strength_is_excluded_from_anchor_intensity": True,
            "bridge_interaction_policy": "ANCHOR_TIMES_BRIDGE_DIVIDED_BY_ANCHOR_PLUS_BRIDGE",
            "event_baseline_policy": "OWN_LOCAL_CONTINUOUS_FLOW_BEFORE_REENTRY_WITHOUT_BRIDGE_BOUNDARY_CONTROL",
            "compound_baseline_policy": "DEDUPLICATED_FLANK_LINK_JOINT_INTENSITY_ACTIVATION_SUPPORT",
            "event_inputs_are_owned_before_aggregation": True,
            "local_combination_policy": "MAX_OWN_CONTINUOUS_OR_COMPOUND_BASE_PLUS_OWN_BOUNDED_EXTRA",
            "whole_candidate_cadence_policy": "MIN_ADJACENT_RELATIVE_INTERVAL_MATCH",
            "contexts_are_repetitions": False,
            "shared_anchor_motions_count_as_repetition": False,
            "isolated_control_peak_policy": "OWN_INTENSITY_LAYER_SUPPORT_WITH_LOCAL_ANCHOR_BOUND",
            "control_support_policy": "INTENSITY_LAYER_INTEGRAL_REFERENCE_TWO_SINGLE_EVENT_ALLOWED",
            "whole_map_axis_used_as_baseline": False,
            "reading_or_tapping_errors_predicted": False,
            "absolute_scale_validated": False,
        },
    }

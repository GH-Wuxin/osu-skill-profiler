"""Shared post-mod local geometry used by published axis calculators."""
from __future__ import annotations

import math
import statistics
from typing import Any, Iterable


def finite(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def angle_delta(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi) / math.pi


def objects(rows: Iterable[dict], resolved_preempt: float | None = None) -> list[dict]:
    """Return ordered object heads and segment boundaries from post-mod rows."""
    result = []
    segment = 0
    last = None
    last_heading = None
    for row in rows:
        if row.get("ls.object_type") == "spinner":
            segment += 1
            last = last_heading = None
            continue
        required = [row.get(key) for key in (
            "ls.start_time_ms", "v091.start_x_px", "v091.start_y_px",
            "ls.radius_px", "ls.preempt_ms")]
        if required[-1] is None:
            required[-1] = resolved_preempt
        if any(finite(value, math.nan) != finite(value, math.inf) for value in required):
            raise ValueError("Local pattern geometry requires finite absolute geometry and preempt")
        time, x, y, radius, preempt = map(float, required)
        if radius <= 0 or preempt <= 0:
            raise ValueError("Local pattern geometry requires positive radius and preempt")
        if last is not None and time <= last["time"]:
            raise ValueError("Local pattern geometry requires strictly ordered hit times")
        dt = time - last["time"] if last else 0.0
        if dt > 1500:
            segment += 1
            last = last_heading = None
        dx, dy = (x - last["x"], y - last["y"]) if last else (0.0, 0.0)
        head_distance = math.hypot(dx, dy)
        heading = math.atan2(dy, dx) if head_distance > .01 else last_heading
        signed_turn = (0.0 if heading is None or last_heading is None else
                       (heading - last_heading + math.pi) % (2 * math.pi) - math.pi)
        distance = max(0.0, finite(row.get("ls.jump_distance_raw_px"), head_distance))
        free_time = max(25.0, finite(row.get("ls.minimum_jump_time_ms"), dt))
        angle = finite(row.get("ls.slider_aware_angle_rad"), math.pi)
        current = dict(time=time, x=x, y=y, radius=radius, preempt=preempt,
                       dt=dt if last else 0.0, segment=segment, distance=distance,
                       head_distance=head_distance, free_time=free_time,
                       turn=clamp(1.0 - angle / math.pi), signed_turn=signed_turn,
                       kind=str(row.get("ls.object_type", "circle")),
                       slider_speed=max(0.0, finite(row.get("ls.slider_velocity_px_per_ms"))),
                       end=max(time, finite(row.get("ls.end_time_ms"), time)))
        result.append(current)
        last, last_heading = current, heading
    return result


def predictability(objects_: list[dict]) -> list[float]:
    """Causal similarity to short translation/rotation/rate-invariant motifs."""
    history: list[tuple] = []
    novelties = []
    last_segment = None
    for obj in objects_:
        if obj["segment"] != last_segment:
            history = []
        last_segment = obj["segment"]
        signature = (math.log2(max(obj["dt"], 25.0)),
                     math.log2(obj["distance"] + 24.0), obj["signed_turn"], obj["kind"])
        history.append(signature)
        errors = []
        for lag in range(1, 5):
            span = max(2, lag)
            if len(history) < span + lag + 1:
                continue
            terms = []
            for k in range(1, span + 1):
                a, b = history[-k], history[-k-lag]
                terms.append(.28*abs(a[0]-b[0]) + .30*abs(a[1]-b[1])
                             + .34*angle_delta(a[2], b[2]) + .08*(a[3] != b[3]))
            errors.append(statistics.fmean(terms))
        novelty = .35 if not errors else -math.expm1(-4.0 * min(errors))
        novelties.append(clamp(novelty))
        history = history[-12:]
    return novelties

"""Slider path geometry for Local Signal Layer v0.3 (v0.2 replayable).

Independent Python reimplementation of the audited ppy/osu slider path
semantics (pinned upstream commit ``b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e``,
difficulty version ``20260706``).  The algorithms follow the audited upstream
definitions:

  - linear sliders are polylines;
  - bezier sliders are a single Bezier curve through all control points,
    adaptively flattened with the 0.25px tolerance used by osu-framework;
  - perfect-curve sliders are circular arcs through 3 points, falling back to
    a Bezier when the arc is degenerate;
  - catmull sliders use the 50-step per-segment Catmull-Rom sampling with the
    stable-style 6px optimisation.

This is an independent implementation from audited semantics (no upstream code
is copied verbatim), so small numeric differences from ppy/osu are possible on
curved paths; straight-line geometry matches exactly.  The parity report and
the golden corpus record the tolerance policy.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

BEZIER_TOLERANCE = 0.25
CATMULL_DETAIL = 50
CIRCULAR_ARC_TOLERANCE = 0.1
DOUBLE_EPSILON = 1e-7
FLOAT_EPSILON = 1e-3
MAX_PATH_CONTROL_POINTS = 4096
MAX_PATH_FLATTEN_WORK = 5_000_000

# Paths above these guards are not flattened.  This is not a statistical clip:
# the slider keeps no fabricated geometry, its local signals become None and a
# provenance flag is attached.  It exists because a single high-degree Bezier
# segment requires O(n^2) work per adaptive subdivision and pathological
# Aspire-style maps (tens of thousands of control points) would otherwise run
# effectively forever.
PATH_BLOCKED_CONTROL_POINTS = "control_points_exceeded"
PATH_BLOCKED_FLATTEN_WORK = "flattening_budget_exceeded"

Vec = tuple[float, float]


class _WorkBudget:
    """Mutable operation counter shared by the flattening helpers."""

    __slots__ = ("remaining", "exceeded")

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        self.exceeded = False

    def spend(self, amount: int) -> None:
        if amount <= 0:
            return
        self.remaining -= amount
        if self.remaining < 0:
            self.exceeded = True
            self.remaining = 0


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Vec, scalar: float) -> Vec:
    return (a[0] * scalar, a[1] * scalar)


def _length(a: Vec) -> float:
    return math.hypot(a[0], a[1])


def _length_sq(a: Vec) -> float:
    return a[0] * a[0] + a[1] * a[1]


def _almost_equals(a: float, b: float, epsilon: float = DOUBLE_EPSILON) -> bool:
    return abs(a - b) <= epsilon


def _definitely_bigger(a: float, b: float, epsilon: float = DOUBLE_EPSILON) -> bool:
    return a - epsilon > b


def _circular_arc_properties(points: list[Vec]) -> dict:
    """Port of osu-framework ``CircularArcProperties`` (audited semantics)."""

    a, b, c = points[0], points[1], points[2]
    cross = (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])
    if _almost_equals(0.0, cross, FLOAT_EPSILON):
        return {
            "valid": False,
            "theta_start": 0.0,
            "theta_range": 0.0,
            "direction": 0.0,
            "radius": 0.0,
            "centre": (0.0, 0.0),
        }
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    a_sq = _length_sq(a)
    b_sq = _length_sq(b)
    c_sq = _length_sq(c)
    centre = (
        (a_sq * (b[1] - c[1]) + b_sq * (c[1] - a[1]) + c_sq * (a[1] - b[1])) / d,
        (a_sq * (c[0] - b[0]) + b_sq * (a[0] - c[0]) + c_sq * (b[0] - a[0])) / d,
    )
    d_a = _sub(a, centre)
    d_c = _sub(c, centre)
    radius = _length(d_a)
    theta_start = math.atan2(d_a[1], d_a[0])
    theta_end = math.atan2(d_c[1], d_c[0])
    while theta_end < theta_start:
        theta_end += 2 * math.pi
    direction = 1.0
    theta_range = theta_end - theta_start
    ortho_a_to_c = (c[1] - a[1], -(c[0] - a[0]))
    if ortho_a_to_c[0] * (b[0] - a[0]) + ortho_a_to_c[1] * (b[1] - a[1]) < 0:
        direction = -1.0
        theta_range = 2 * math.pi - theta_range
    return {
        "valid": True,
        "theta_start": theta_start,
        "theta_range": theta_range,
        "direction": direction,
        "radius": radius,
        "centre": centre,
    }


def _bezier_is_flat_enough(control_points: list[Vec]) -> bool:
    for i in range(1, len(control_points) - 1):
        second = (
            control_points[i - 1][0] - 2 * control_points[i][0] + control_points[i + 1][0],
            control_points[i - 1][1] - 2 * control_points[i][1] + control_points[i + 1][1],
        )
        if _length_sq(second) > BEZIER_TOLERANCE * BEZIER_TOLERANCE * 4:
            return False
    return True


def _bezier_subdivide(
    control_points: list[Vec],
    left: list[Vec],
    right: list[Vec],
    midpoints: list[Vec],
    budget: _WorkBudget | None = None,
) -> None:
    count = len(control_points)
    if budget is not None:
        budget.spend((count * (count - 1)) // 2)
    for i in range(count):
        midpoints[i] = control_points[i]
    for i in range(count):
        left[i] = midpoints[0]
        right[count - i - 1] = midpoints[count - i - 1]
        for j in range(count - i - 1):
            midpoints[j] = (
                (midpoints[j][0] + midpoints[j + 1][0]) / 2,
                (midpoints[j][1] + midpoints[j + 1][1]) / 2,
            )


def _bezier_approximate(control_points: list[Vec], output: list[Vec], buffer1: list[Vec], buffer2: list[Vec]) -> None:
    count = len(control_points)
    left = buffer2
    right = buffer1
    midpoints = buffer1
    _bezier_subdivide(control_points, left, right, midpoints)
    for i in range(count - 1):
        left[count + i] = right[i + 1]
    output.append(control_points[0])
    for i in range(1, count - 1):
        index = 2 * i
        point = (
            0.25 * (left[index - 1][0] + 2 * left[index][0] + left[index + 1][0]),
            0.25 * (left[index - 1][1] + 2 * left[index][1] + left[index + 1][1]),
        )
        output.append(point)


def _bspline_to_bezier_internal(control_points: list[Vec], degree: int, budget: _WorkBudget | None = None) -> list[list[Vec]]:
    """Port of osu-framework ``BSplineToBezier`` internal Boehm subdivision."""

    point_count = len(control_points) - 1
    degree = min(degree, point_count)
    points = [list(p) for p in control_points]
    if degree == point_count:
        return [[tuple(p) for p in points]]
    if budget is not None:
        budget.spend((point_count - degree) * degree * degree)
        if budget.exceeded:
            return []
    result: list[list[Vec]] = []
    for i in range(point_count - degree):
        sub_bezier: list[Vec] = [points[i]]
        for j in range(degree - 1):
            sub_bezier.append(points[i + 1])
            for k in range(1, degree - j):
                l = min(k, point_count - degree - i)
                points[i + k] = (
                    (l * points[i + k][0] + points[i + k + 1][0]) / (l + 1),
                    (l * points[i + k][1] + points[i + k + 1][1]) / (l + 1),
                )
        sub_bezier.append(points[i + 1])
        result.append(sub_bezier)
    result.append(points[point_count - degree:])
    return result


def _bspline_to_piecewise_linear(control_points: list[Vec], degree: int, budget: _WorkBudget | None = None) -> list[Vec]:
    """Adaptive flattening of a clamped uniform B-spline (audited port)."""

    if len(control_points) < 2:
        return [p for p in control_points]
    degree = min(degree, len(control_points) - 1)
    if budget is not None and budget.exceeded:
        return []
    output: list[Vec] = []
    to_flatten: list[list[Vec]] = []
    for segment in reversed(_bspline_to_bezier_internal(control_points, degree, budget)):
        to_flatten.append(segment)
    if budget is not None and budget.exceeded:
        return []
    subdivision_buffer1 = [(0.0, 0.0)] * (degree + 1)
    subdivision_buffer2 = [(0.0, 0.0)] * (degree * 2 + 1)
    while to_flatten:
        if budget is not None and budget.exceeded:
            return []
        parent = to_flatten.pop()
        if _bezier_is_flat_enough(parent):
            _bezier_approximate(parent, output, subdivision_buffer1, subdivision_buffer2)
            continue
        left_child = [(0.0, 0.0)] * (degree + 1)
        right_child = [(0.0, 0.0)] * (degree + 1)
        _bezier_subdivide(parent, left_child, right_child, subdivision_buffer1, budget)
        for i in range(degree + 1):
            parent[i] = left_child[i]
        to_flatten.append(right_child)
        to_flatten.append(parent)
    output.append(control_points[-1])
    return output


def _catmull_find_point(v1: Vec, v2: Vec, v3: Vec, v4: Vec, t: float) -> Vec:
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        2 * v2[0]
        + (-v1[0] + v3[0]) * t
        + (2 * v1[0] - 5 * v2[0] + 4 * v3[0] - v4[0]) * t2
        + (-v1[0] + 3 * v2[0] - 3 * v3[0] + v4[0]) * t3
    )
    y = 0.5 * (
        2 * v2[1]
        + (-v1[1] + v3[1]) * t
        + (2 * v1[1] - 5 * v2[1] + 4 * v3[1] - v4[1]) * t2
        + (-v1[1] + 3 * v2[1] - 3 * v3[1] + v4[1]) * t3
    )
    return (x, y)


def _catmull_to_piecewise_linear(control_points: list[Vec]) -> list[Vec]:
    result: list[Vec] = []
    for i in range(len(control_points) - 1):
        v1 = control_points[i - 1] if i > 0 else control_points[i]
        v2 = control_points[i]
        v3 = control_points[i + 1] if i < len(control_points) - 1 else _sub(_mul(v2, 2), v1)
        v4 = control_points[i + 2] if i < len(control_points) - 2 else _sub(_mul(v3, 2), v2)
        for c in range(CATMULL_DETAIL):
            result.append(_catmull_find_point(v1, v2, v3, v4, c / CATMULL_DETAIL))
            result.append(_catmull_find_point(v1, v2, v3, v4, (c + 1) / CATMULL_DETAIL))
    return result


def _optimise_catmull(sub_path: list[Vec]) -> tuple[list[Vec], float]:
    """Stable-style 6px Catmull optimisation used by pinned ppy/osu."""

    optimised: list[Vec] = []
    optimised_length = 0.0
    last_start: Optional[Vec] = None
    length_removed_since_start = 0.0
    catmull_segment_length = CATMULL_DETAIL * 2
    for i, point in enumerate(sub_path):
        if last_start is None:
            optimised.append(point)
            last_start = point
            continue
        dist_from_start = _length(_sub(last_start, point))
        length_removed_since_start += _length(_sub(sub_path[i - 1], point))
        if (
            dist_from_start > 6
            or (i + 1) % catmull_segment_length == 0
            or i == len(sub_path) - 1
        ):
            optimised.append(point)
            optimised_length += length_removed_since_start - dist_from_start
            last_start = None
            length_removed_since_start = 0.0
    return optimised, optimised_length


@dataclass(frozen=True)
class SliderPath:
    """Port of the audited ``SliderPath`` geometry used by difficulty."""

    control_points: tuple[Vec, ...]
    curve_type: str
    expected_distance: Optional[float] = None

    # populated lazily and cached
    _calculated_path: tuple[Vec, ...] = field(default=(), init=False, repr=False)
    _cumulative_length: tuple[float, ...] = field(default=(), init=False, repr=False)
    _calculated_length: float = field(default=0.0, init=False, repr=False)
    _distance: Optional[float] = field(default=None, init=False, repr=False)
    _non_finite: bool = field(default=False, init=False, repr=False)
    _blocked_reason: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.curve_type not in ("L", "B", "P", "C"):
            # Unknown single-letter curve types from degenerate maps fall back
            # to linear geometry, matching the lenient parser behaviour.
            object.__setattr__(self, "curve_type", "L")
        if self.expected_distance is not None and not math.isfinite(self.expected_distance):
            object.__setattr__(self, "expected_distance", None)
            object.__setattr__(self, "_non_finite", True)

    @property
    def non_finite_input(self) -> bool:
        return self._non_finite

    @property
    def blocked_reason(self) -> Optional[str]:
        """Non-None when the path is too complex to flatten safely."""

        return self._blocked_reason

    @property
    def distance(self) -> float:
        self._ensure_valid()
        return self._distance if self._distance is not None else 0.0

    @property
    def calculated_distance(self) -> float:
        self._ensure_valid()
        return self._calculated_length

    @property
    def calculated_path(self) -> tuple[Vec, ...]:
        self._ensure_valid()
        return self._calculated_path

    def position_at(self, progress: float) -> Vec:
        self._ensure_valid()
        d = max(0.0, min(1.0, progress)) * self.distance
        path = self._calculated_path
        if not path:
            return (0.0, 0.0)
        return self._interpolate_vertices(self._index_of_distance(d), d)

    def _ensure_valid(self) -> None:
        if self._distance is not None:
            return
        points = [p for p in self.control_points]
        if not points:
            points = [(0.0, 0.0)]
        if len(points) > MAX_PATH_CONTROL_POINTS:
            object.__setattr__(self, "_blocked_reason", PATH_BLOCKED_CONTROL_POINTS)
            object.__setattr__(self, "_distance", 0.0)
            object.__setattr__(self, "_calculated_path", ())
            object.__setattr__(self, "_cumulative_length", ())
            object.__setattr__(self, "_calculated_length", 0.0)
            return
        budget = _WorkBudget(MAX_PATH_FLATTEN_WORK)
        sub_path: list[Vec]
        optimised_length = 0.0
        if self.curve_type == "L" or len(points) == 1:
            sub_path = [p for p in points]
        elif self.curve_type == "B":
            sub_path = _bspline_to_piecewise_linear(points, max(1, len(points) - 1), budget)
        elif self.curve_type == "P":
            arc: Optional[dict] = None
            if len(points) == 3:
                arc = _circular_arc_properties(points)
                if arc["valid"]:
                    amount_points = (
                        2
                        if 2 * arc["radius"] <= CIRCULAR_ARC_TOLERANCE
                        else max(2, int(math.ceil(arc["theta_range"] / (2 * math.acos(1 - CIRCULAR_ARC_TOLERANCE / arc["radius"])))))
                    )
                    if amount_points >= 1000:
                        arc = None
            if arc is None or not arc["valid"]:
                sub_path = _bspline_to_piecewise_linear(points, len(points), budget)
            else:
                sub_path = []
                for i in range(amount_points):
                    fract = i / (amount_points - 1)
                    theta = arc["theta_start"] + arc["direction"] * fract * arc["theta_range"]
                    sub_path.append(
                        (
                            arc["centre"][0] + math.cos(theta) * arc["radius"],
                            arc["centre"][1] + math.sin(theta) * arc["radius"],
                        )
                    )
        else:  # Catmull
            sub_path, optimised_length = _optimise_catmull(_catmull_to_piecewise_linear(points))

        if budget.exceeded:
            object.__setattr__(self, "_blocked_reason", PATH_BLOCKED_FLATTEN_WORK)
            object.__setattr__(self, "_distance", 0.0)
            object.__setattr__(self, "_calculated_path", ())
            object.__setattr__(self, "_cumulative_length", ())
            object.__setattr__(self, "_calculated_length", 0.0)
            return

        # Drop consecutive duplicate points across segments (single segment for
        # .osu sliders, kept for structural parity with the audited builder).
        cleaned: list[Vec] = []
        for point in sub_path:
            if not cleaned or cleaned[-1] != point:
                cleaned.append(point)
        if not cleaned:
            cleaned = [(0.0, 0.0)]

        calculated_length = optimised_length
        cumulative: list[float] = [0.0]
        for i in range(len(cleaned) - 1):
            calculated_length += _length(_sub(cleaned[i + 1], cleaned[i]))
            cumulative.append(calculated_length)

        expected = self.expected_distance
        if expected is not None and calculated_length != expected:
            if len(cleaned) >= 2 and cleaned[-1] == cleaned[-2] and expected > calculated_length:
                cumulative.append(calculated_length)
            else:
                cumulative.pop()
                path_end_index = len(cleaned) - 1
                if calculated_length > expected:
                    while cumulative and cumulative[-1] >= expected:
                        cumulative.pop()
                        cleaned.pop()
                        path_end_index -= 1
                if path_end_index <= 0:
                    cumulative.append(0.0)
                else:
                    direction = _sub(cleaned[path_end_index], cleaned[path_end_index - 1])
                    direction_length = _length(direction)
                    if direction_length <= 0:
                        cumulative.append(expected)
                    else:
                        direction = _mul(direction, 1.0 / direction_length)
                        cleaned[path_end_index] = _add(cleaned[path_end_index - 1], _mul(direction, expected - cumulative[-1]))
                        cumulative.append(expected)

        object.__setattr__(self, "_calculated_path", tuple(cleaned))
        object.__setattr__(self, "_cumulative_length", tuple(cumulative))
        object.__setattr__(self, "_calculated_length", calculated_length)
        object.__setattr__(self, "_distance", cumulative[-1] if cumulative else 0.0)

    def _index_of_distance(self, d: float) -> int:
        cumulative = self._cumulative_length
        if not cumulative:
            return 0
        i = bisect.bisect_left(cumulative, d)
        return i

    def _interpolate_vertices(self, index: int, d: float) -> Vec:
        path = self._calculated_path
        cumulative = self._cumulative_length
        if index <= 0:
            return path[0]
        if index >= len(path):
            return path[-1]
        p0 = path[index - 1]
        p1 = path[index]
        d0 = cumulative[index - 1]
        d1 = cumulative[index]
        if _almost_equals(d0, d1):
            return p0
        w = (d - d0) / (d1 - d0)
        return (p0[0] + (p1[0] - p0[0]) * w, p0[1] + (p1[1] - p0[1]) * w)


def build_slider_path(
    curve_type: str | None,
    control_points: Iterable[tuple[float, float]],
    expected_distance: float | None,
) -> SliderPath:
    """Build a path-relative ``SliderPath`` from parsed slider data."""

    points = [(float(x), float(y)) for x, y in control_points]
    if not points:
        points = [(0.0, 0.0)]
    return SliderPath(tuple(points), curve_type or "L", expected_distance)


__all__ = ["SliderPath", "build_slider_path"]

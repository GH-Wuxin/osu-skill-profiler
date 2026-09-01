"""Small synthetic rows shared by published local-pattern tests."""
import math
import random


def rows_for(points, intervals=None, preempt=750.0, radius=36.5):
    intervals = intervals or [125.0] * (len(points)-1)
    rows, time, heading = [], 0.0, None
    for index, (x, y) in enumerate(points):
        dt = intervals[index-1] if index else 0
        time += dt
        distance = math.dist(points[index-1], points[index]) if index else 0
        direction = math.atan2(y-points[index-1][1], x-points[index-1][0]) if index else None
        turn = 0 if index < 2 else abs((direction-heading+math.pi) % (2*math.pi)-math.pi)
        rows.append({"ls.object_type":"circle", "ls.start_time_ms":time,
                     "ls.end_time_ms":time, "ls.delta_time_ms":dt,
                     "ls.adjusted_delta_time_ms":dt, "ls.minimum_jump_time_ms":dt,
                     "ls.radius_px":radius, "ls.preempt_ms":preempt,
                     "v091.start_x_px":x, "v091.start_y_px":y,
                     "ls.jump_distance_raw_px":distance,
                     "ls.slider_aware_angle_rad":math.pi-turn})
        heading = direction
    return rows


def folded(count=80):
    rng = random.Random(3417)
    return [(256+rng.uniform(-65, 65), 192+rng.uniform(-65, 65)) for _ in range(count)]

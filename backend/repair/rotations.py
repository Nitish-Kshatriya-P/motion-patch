import math
from typing import List, Tuple, Any

def quat_mult(q1: List[float], q2: List[float]) -> List[float]:
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return [
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ]

def quat_normalize(q: List[float]) -> List[float]:
    norm = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    if norm < 1e-12:
        return [1.0, 0.0, 0.0, 0.0]
    return [q[0] / norm, q[1] / norm, q[2] / norm, q[3] / norm]

def normalize_rotation_order(order: Any) -> str:
    if isinstance(order, (list, tuple)):
        return "".join(c[0].upper() for c in order if c)
    return "".join(c.upper() for c in order if c.upper() in ("X", "Y", "Z"))

def axis_angle_to_quat(axis: str, deg: float) -> List[float]:
    rad = math.radians(deg) * 0.5
    s = math.sin(rad)
    c = math.cos(rad)
    ax = axis[0].upper() if axis else "X"
    if ax == "X":
        return [c, s, 0.0, 0.0]
    elif ax == "Y":
        return [c, 0.0, s, 0.0]
    elif ax == "Z":
        return [c, 0.0, 0.0, s]
    return [1.0, 0.0, 0.0, 0.0]

def euler_to_quaternion(euler_degrees: List[float], order: Any) -> List[float]:
    order_str = normalize_rotation_order(order)
    q = [1.0, 0.0, 0.0, 0.0]
    for axis, deg in zip(order_str, euler_degrees):
        q = quat_mult(q, axis_angle_to_quat(axis, deg))
    return quat_normalize(q)

def quat_to_matrix(q: List[float]) -> List[List[float]]:
    w, x, y, z = quat_normalize(q)
    return [
        [
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y - w * z),
            2.0 * (x * z + w * y),
        ],
        [
            2.0 * (x * y + w * z),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z - w * x),
        ],
        [
            2.0 * (x * z - w * y),
            2.0 * (y * z + w * x),
            1.0 - 2.0 * (x * x + y * y),
        ],
    ]

def matrix_to_euler(m: List[List[float]], order: Any) -> List[float]:
    order_up = normalize_rotation_order(order)
    if order_up == "ZXY":
        sy = min(1.0, max(-1.0, m[2][1]))
        x = math.degrees(math.asin(sy))
        if abs(math.cos(math.radians(x))) > 1e-6:
            z = math.degrees(math.atan2(-m[0][1], m[1][1]))
            y = math.degrees(math.atan2(-m[2][0], m[2][2]))
        else:
            z = math.degrees(math.atan2(m[1][0], m[0][0]))
            y = 0.0
        return [z, x, y]
    elif order_up == "ZYX":
        sy = min(1.0, max(-1.0, -m[2][0]))
        y = math.degrees(math.asin(sy))
        if abs(math.cos(math.radians(y))) > 1e-6:
            z = math.degrees(math.atan2(m[1][0], m[0][0]))
            x = math.degrees(math.atan2(m[2][1], m[2][2]))
        else:
            z = math.degrees(math.atan2(-m[0][1], m[1][1]))
            x = 0.0
        return [z, y, x]
    elif order_up == "XYZ":
        sy = min(1.0, max(-1.0, m[0][2]))
        y = math.degrees(math.asin(sy))
        if abs(math.cos(math.radians(y))) > 1e-6:
            x = math.degrees(math.atan2(-m[1][2], m[2][2]))
            z = math.degrees(math.atan2(-m[0][1], m[0][0]))
        else:
            x = math.degrees(math.atan2(m[1][0], m[1][1]))
            z = 0.0
        return [x, y, z]
    elif order_up == "YXZ":
        sy = min(1.0, max(-1.0, -m[1][2]))
        x = math.degrees(math.asin(sy))
        if abs(math.cos(math.radians(x))) > 1e-6:
            y = math.degrees(math.atan2(m[0][2], m[2][2]))
            z = math.degrees(math.atan2(m[1][0], m[1][1]))
        else:
            y = math.degrees(math.atan2(-m[2][0], m[0][0]))
            z = 0.0
        return [y, x, z]
    else:
        sy = min(1.0, max(-1.0, m[2][1]))
        x = math.degrees(math.asin(sy))
        z = math.degrees(math.atan2(-m[0][1], m[1][1]))
        y = math.degrees(math.atan2(-m[2][0], m[2][2]))
        return [z, x, y]

def quaternion_to_euler(q: List[float], order: Any) -> List[float]:
    m = quat_to_matrix(q)
    return matrix_to_euler(m, order)

def quaternion_angular_distance(q1: List[float], q2: List[float]) -> float:
    dot = abs(q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3])
    dot = min(1.0, max(-1.0, dot))
    return 2.0 * math.degrees(math.acos(dot))

def slerp(q0: List[float], q1: List[float], t: float) -> List[float]:
    q0 = quat_normalize(q0)
    q1 = quat_normalize(q1)
    dot = q0[0] * q1[0] + q0[1] * q1[1] + q0[2] * q1[2] + q0[3] * q1[3]

    if dot < 0.0:
        q1 = [-c for c in q1]
        dot = -dot

    if dot > 0.9995:
        res = [
            q0[0] + t * (q1[0] - q0[0]),
            q0[1] + t * (q1[1] - q0[1]),
            q0[2] + t * (q1[2] - q0[2]),
            q0[3] + t * (q1[3] - q0[3]),
        ]
        return quat_normalize(res)

    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    sin_theta = math.sin(theta)

    s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
    s1 = sin_theta / sin_theta_0

    return [
        s0 * q0[0] + s1 * q1[0],
        s0 * q0[1] + s1 * q1[1],
        s0 * q0[2] + s1 * q1[2],
        s0 * q0[3] + s1 * q1[3],
    ]

def select_closest_euler(target_euler: List[float], reference_euler: List[float]) -> List[float]:
    res = []
    for tgt, ref in zip(target_euler, reference_euler):
        best_val = tgt
        best_diff = abs(tgt - ref)
        for k in (-2, -1, 1, 2):
            cand = tgt + k * 360.0
            diff = abs(cand - ref)
            if diff < best_diff:
                best_diff = diff
                best_val = cand
        res.append(best_val)
    return res

def unwrap_euler_trajectory(trajectory: List[List[float]]) -> List[List[float]]:
    if not trajectory:
        return []
    unwrapped = [list(trajectory[0])]
    for i in range(1, len(trajectory)):
        prev = unwrapped[-1]
        curr = trajectory[i]
        unwrapped.append(select_closest_euler(curr, prev))
    return unwrapped

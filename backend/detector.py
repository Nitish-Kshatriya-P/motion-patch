import math
import json
import hashlib
import copy
from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel, Field

from models import (
    AnomalyType,
    Severity,
    BodyPart,
    Finding,
    Analysis,
    AnalysisStatus,
    AssessmentVerdict,
    BVHMetadata,
    AgentSpecification,
    compute_roster_hash,
)
from bvh_parser import ParsedBVH, JointNode

DETECTOR_VERSION = "1.0.0"


class WholeClipStatistics(BaseModel):
    floor_y_p20: float = 0.0
    floor_y_p05: float = 0.0
    root_trans_threshold: float = 0.0
    root_rot_threshold: float = 0.0
    root_moves: bool = False
    channel_max_rot_diff: Dict[int, float] = Field(default_factory=dict)
    jitter_thresholds: Dict[str, Tuple[float, float]] = Field(default_factory=dict)
    pop_thresholds: Dict[str, Tuple[float, float]] = Field(default_factory=dict)


class JitterFindingSpec(BaseModel):
    joint_name: str
    body_part: BodyPart
    anomaly_type: AnomalyType
    channel_name: str
    threshold: float
    dt: float
    unit: str
    mad_acc: Optional[float] = None


def unwrap_angles(angles: List[float]) -> List[float]:
    if not angles:
        return []
    unwrapped = [angles[0]]
    for t in range(1, len(angles)):
        diff = angles[t] - angles[t - 1]
        diff_unwrapped = (diff + 180.0) % 360.0 - 180.0
        unwrapped.append(unwrapped[-1] + diff_unwrapped)
    return unwrapped


def calc_median(vals: List[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = int(n / 2)
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def calc_mad(vals: List[float], median_val: float) -> float:
    if not vals:
        return 0.0
    abs_diffs = [abs(v - median_val) for v in vals]
    return calc_median(abs_diffs)


def merge_frame_intervals(frame_indices: List[int], max_gap: int = 2) -> List[Tuple[int, int]]:
    if not frame_indices:
        return []
    sorted_frames = sorted(set(frame_indices))
    intervals: List[Tuple[int, int]] = []
    start = sorted_frames[0]
    end = sorted_frames[0]
    for f in sorted_frames[1:]:
        if f <= end + max_gap:
            end = f
        else:
            intervals.append((start, end))
            start = f
            end = f
    intervals.append((start, end))
    return intervals


def rotation_matrix_x(deg: float) -> List[List[float]]:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def rotation_matrix_y(deg: float) -> List[List[float]]:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def rotation_matrix_z(deg: float) -> List[List[float]]:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def mat_mul_3x3(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [
        [
            a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j]
            for j in range(3)
        ]
        for i in range(3)
    ]


def mat_vec_mul_3x3(m: List[List[float]], v: List[float]) -> List[float]:
    return [
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    ]


def vec_sub(a: List[float], b: List[float]) -> List[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def vec_add(a: List[float], b: List[float]) -> List[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def vec_scale(a: List[float], s: float) -> List[float]:
    return [a[0] * s, a[1] * s, a[2] * s]


def vec_dot(a: List[float], b: List[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def vec_norm(a: List[float]) -> float:
    return math.sqrt(vec_dot(a, a))


def vec_dist(a: List[float], b: List[float]) -> float:
    return vec_norm(vec_sub(a, b))


def clamp_val(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def segment_segment_distance(
    p1: List[float], p2: List[float], q1: List[float], q2: List[float]
) -> float:
    u = vec_sub(p2, p1)
    v = vec_sub(q2, q1)
    w0 = vec_sub(p1, q1)
    a = vec_dot(u, u)
    b = vec_dot(u, v)
    c = vec_dot(v, v)
    d = vec_dot(u, w0)
    e = vec_dot(v, w0)
    denom = a * c - b * b
    sc = 0.0
    tc = 0.0

    if denom < 1e-8:
        sc = 0.0
        tc = e / c if c > 1e-8 else 0.0
    else:
        sc = (b * e - c * d) / denom
        tc = (a * e - b * d) / denom

    sc = clamp_val(sc, 0.0, 1.0)
    tc = clamp_val(tc, 0.0, 1.0)

    close_p = vec_add(p1, vec_scale(u, sc))
    close_q = vec_add(q1, vec_scale(v, tc))
    return vec_dist(close_p, close_q)


def detect_coordinate_profile(parsed: ParsedBVH) -> str:
    if not parsed.ordered_joints:
        return "Y"

    xs = [j.global_rest_position[0] for j in parsed.ordered_joints]
    ys = [j.global_rest_position[1] for j in parsed.ordered_joints]
    zs = [j.global_rest_position[2] for j in parsed.ordered_joints]

    extent_x = max(xs) - min(xs)
    extent_y = max(ys) - min(ys)
    extent_z = max(zs) - min(zs)

    if extent_z > extent_y and extent_z > extent_x:
        return "Z"
    return "Y"


def identity_matrix_3x3() -> List[List[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def transpose_3x3(m: List[List[float]]) -> List[List[float]]:
    return [[m[j][i] for j in range(3)] for i in range(3)]


def so3_geodesic_distance(r1: List[List[float]], r2: List[List[float]]) -> float:
    r_rel = mat_mul_3x3(r2, transpose_3x3(r1))
    tr = r_rel[0][0] + r_rel[1][1] + r_rel[2][2]
    cos_phi = clamp_val((tr - 1.0) / 2.0, -1.0, 1.0)
    return math.degrees(math.acos(cos_phi))


def slerp_rotations(
    r1: List[List[float]],
    r2: List[List[float]],
    u: float,
) -> List[List[float]]:
    if u <= 0.0:
        return r1
    if u >= 1.0:
        return r2
    r_rel = mat_mul_3x3(r2, transpose_3x3(r1))
    tr = r_rel[0][0] + r_rel[1][1] + r_rel[2][2]
    cos_phi = clamp_val((tr - 1.0) / 2.0, -1.0, 1.0)
    phi = math.acos(cos_phi)
    if phi < 1e-5:
        return r1
    sin_phi = math.sin(phi)
    rx = (r_rel[2][1] - r_rel[1][2]) / (2.0 * sin_phi)
    ry = (r_rel[0][2] - r_rel[2][0]) / (2.0 * sin_phi)
    rz = (r_rel[1][0] - r_rel[0][1]) / (2.0 * sin_phi)
    norm = math.sqrt(rx * rx + ry * ry + rz * rz)
    if norm < 1e-6:
        return r1
    rx, ry, rz = rx / norm, ry / norm, rz / norm
    angle = u * phi
    c = math.cos(angle)
    s = math.sin(angle)
    c1 = 1.0 - c
    r_step = [
        [c + rx * rx * c1, rx * ry * c1 - rz * s, rx * rz * c1 + ry * s],
        [ry * rx * c1 + rz * s, c + ry * ry * c1, ry * rz * c1 - rx * s],
        [rz * rx * c1 - ry * s, rz * ry * c1 + rx * s, c + rz * rz * c1],
    ]
    return mat_mul_3x3(r_step, r1)


def transform_vector_z_to_y(v: List[float]) -> List[float]:
    return [v[0], v[2], -v[1]]


def transform_matrix_z_to_y(m: List[List[float]]) -> List[List[float]]:
    m_rot = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]
    m_rot_t = [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]
    return mat_mul_3x3(m_rot, mat_mul_3x3(m, m_rot_t))


def compute_joint_rotation_matrix(joint: JointNode, frame_motion: List[float]) -> List[List[float]]:
    mat = identity_matrix_3x3()
    for ch_name, ch_idx in zip(joint.channels, joint.channel_indices):
        deg = frame_motion[ch_idx]
        if ch_name == "Xrotation":
            mat = mat_mul_3x3(mat, rotation_matrix_x(deg))
        elif ch_name == "Yrotation":
            mat = mat_mul_3x3(mat, rotation_matrix_y(deg))
        elif ch_name == "Zrotation":
            mat = mat_mul_3x3(mat, rotation_matrix_z(deg))
    return mat


def slice_parsed_bvh(parsed: ParsedBVH, start_frame: int, end_frame: int) -> ParsedBVH:
    sliced_motion = parsed.motion[start_frame:end_frame]
    fc = len(sliced_motion)
    meta = BVHMetadata(
        parser_version=parsed.metadata.parser_version,
        skeleton_signature=parsed.metadata.skeleton_signature,
        root_name=parsed.metadata.root_name,
        joints=parsed.metadata.joints,
        channel_order=parsed.metadata.channel_order,
        total_channels=parsed.metadata.total_channels,
        frame_count=fc,
        frame_time=parsed.metadata.frame_time,
        duration_seconds=round(fc * parsed.metadata.frame_time, 6),
        skeleton_scale=parsed.metadata.skeleton_scale,
    )
    return ParsedBVH(
        root_node=parsed.root_node,
        joint_map=parsed.joint_map,
        ordered_joints=parsed.ordered_joints,
        motion=sliced_motion,
        metadata=meta,
        raw_content_hash=parsed.raw_content_hash,
    )


def extract_whole_clip_statistics(parsed: ParsedBVH) -> WholeClipStatistics:
    dt = parsed.metadata.frame_time
    fc = parsed.metadata.frame_count
    scale = parsed.metadata.skeleton_scale
    root = parsed.root_node

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_nodes = [j for j in parsed.ordered_joints if j.name.lower().replace(" ", "").replace("_", "") in candidate_foot_names]
    needed_joints = set()
    for fn in foot_nodes:
        curr = fn
        while curr:
            needed_joints.add(curr.name)
            curr = parsed.joint_map.get(curr.parent_name) if curr.parent_name else None

    is_norm = bool(detect_coordinate_profile(parsed) == "Z")
    foot_positions_y: Dict[str, List[float]] = {fn.name: [] for fn in foot_nodes}
    for frame_motion in parsed.motion:
        rx, ry, rz = 0.0, 0.0, 0.0
        for ch_name, ch_idx in zip(root.channels, root.channel_indices):
            if ch_name == "Xposition":
                rx = frame_motion[ch_idx]
            elif ch_name == "Yposition":
                ry = frame_motion[ch_idx]
            elif ch_name == "Zposition":
                rz = frame_motion[ch_idx]
        root_local_raw = [root.offset[0] + rx, root.offset[1] + ry, root.offset[2] + rz]
        root_raw_rot = compute_joint_rotation_matrix(root, frame_motion)
        root_pos = transform_vector_z_to_y(root_local_raw) if is_norm else root_local_raw
        root_rot = transform_matrix_z_to_y(root_raw_rot) if is_norm else root_raw_rot

        def prop(node: JointNode, p_pos: List[float], p_rot: List[List[float]]):
            for ch in node.children:
                if ch.name not in needed_joints:
                    continue
                c_off = transform_vector_z_to_y(ch.offset) if is_norm else ch.offset
                c_rot = compute_joint_rotation_matrix(ch, frame_motion)
                if is_norm:
                    c_rot = transform_matrix_z_to_y(c_rot)
                c_pos = vec_add(p_pos, mat_vec_mul_3x3(p_rot, c_off))
                world_rot = mat_mul_3x3(p_rot, c_rot)
                if ch.name in foot_positions_y:
                    foot_positions_y[ch.name].append(c_pos[1])
                prop(ch, c_pos, world_rot)

        prop(root, root_pos, root_rot)

    all_foot_y: List[float] = []
    for fn in foot_nodes:
        all_foot_y.extend(foot_positions_y[fn.name])
    sorted_y = sorted(all_foot_y)
    floor_y_p20 = sorted_y[max(0, int(len(sorted_y) * 0.20))] if sorted_y else 0.0
    floor_y_p05 = sorted_y[max(0, int(len(sorted_y) * 0.05))] if sorted_y else 0.0

    trans_indices = [idx for name, idx in zip(root.channels, root.channel_indices) if "position" in name.lower()]
    root_trans_threshold = scale * 2.0
    if len(trans_indices) >= 3 and fc >= 3:
        speeds: List[float] = []
        for t in range(1, fc):
            prev_m = parsed.motion[t - 1]
            curr_m = parsed.motion[t]
            dx = curr_m[trans_indices[0]] - prev_m[trans_indices[0]]
            dy = curr_m[trans_indices[1]] - prev_m[trans_indices[1]]
            dz = curr_m[trans_indices[2]] - prev_m[trans_indices[2]]
            speeds.append(math.sqrt(dx * dx + dy * dy + dz * dz) / dt)
        med_s = calc_median(speeds)
        root_trans_threshold = max(5.0 * med_s, scale * 2.0)

    rot_indices = [idx for name, idx in zip(root.channels, root.channel_indices) if "rotation" in name.lower()]
    root_rot_threshold = 450.0
    if len(rot_indices) >= 3 and fc >= 5:
        rot_speeds: List[float] = []
        for t in range(1, fc):
            r_prev = compute_joint_rotation_matrix(root, parsed.motion[t - 1])
            r_curr = compute_joint_rotation_matrix(root, parsed.motion[t])
            rot_speeds.append(so3_geodesic_distance(r_prev, r_curr) / dt)
        med_w = calc_median(rot_speeds[1:]) if len(rot_speeds) > 1 else 0.0
        mad_w = calc_mad(rot_speeds[1:], med_w) if len(rot_speeds) > 1 else 0.0
        root_rot_threshold = max(450.0, med_w + 6.0 * max(mad_w, 5.0))

    root_disp = 0.0
    if len(trans_indices) >= 3 and fc >= 2:
        for t in range(1, fc):
            dx = parsed.motion[t][trans_indices[0]] - parsed.motion[t - 1][trans_indices[0]]
            dy = parsed.motion[t][trans_indices[1]] - parsed.motion[t - 1][trans_indices[1]]
            dz = parsed.motion[t][trans_indices[2]] - parsed.motion[t - 1][trans_indices[2]]
            root_disp += math.sqrt(dx * dx + dy * dy + dz * dz)
    root_moves = root_disp > scale * 0.05

    channel_max_rot_diff: Dict[int, float] = {}
    for j in parsed.ordered_joints:
        for ch_name, ch_idx in zip(j.channels, j.channel_indices):
            if "rotation" in ch_name.lower():
                vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                channel_max_rot_diff[ch_idx] = max(vals) - min(vals)

    jitter_thresholds: Dict[str, Tuple[float, float]] = {}
    for j in parsed.ordered_joints:
        for ch_name, ch_idx in zip(j.channels, j.channel_indices):
            is_rot = "rotation" in ch_name.lower()
            is_trans = "position" in ch_name.lower()
            if not (is_rot or is_trans):
                continue
            series = [parsed.motion[t][ch_idx] for t in range(fc)]
            dt2 = dt * dt
            accs: List[float] = []
            for t in range(1, fc - 1):
                if is_rot:
                    d1 = (series[t] - series[t - 1] + 180.0) % 360.0 - 180.0
                    d2 = (series[t + 1] - series[t] + 180.0) % 360.0 - 180.0
                else:
                    d1 = series[t] - series[t - 1]
                    d2 = series[t + 1] - series[t]
                accs.append((d2 - d1) / dt2)
            if accs:
                med = calc_median(accs)
                mad = calc_mad(accs, med)
                min_acc = 700.0 if is_rot else 40.0
                thresh = max(4.0 * mad, min_acc)
                jitter_thresholds[f"{j.name}:{ch_name}"] = (thresh, mad)

    pop_thresholds: Dict[str, Tuple[float, float]] = {}
    for j in parsed.ordered_joints:
        rots = [compute_joint_rotation_matrix(j, parsed.motion[t]) for t in range(fc)]
        steps = [so3_geodesic_distance(rots[t - 1], rots[t]) for t in range(1, fc)]
        if steps:
            med_s = calc_median(steps)
            mad_s = calc_mad(steps, med_s)
            thresh_s = max(8.0, med_s + 5.0 * max(mad_s, 0.5))
            step_accels = [abs(steps[t] - steps[t - 1]) / dt for t in range(1, len(steps))]
            med_a = calc_median(step_accels)
            mad_a = calc_mad(step_accels, med_a)
            thresh_a = max(12000.0, 5.0 * max(mad_a, 500.0))
            pop_thresholds[j.name] = (thresh_s, thresh_a)

    return WholeClipStatistics(
        floor_y_p20=floor_y_p20,
        floor_y_p05=floor_y_p05,
        root_trans_threshold=root_trans_threshold,
        root_rot_threshold=root_rot_threshold,
        root_moves=root_moves,
        channel_max_rot_diff=channel_max_rot_diff,
        jitter_thresholds=jitter_thresholds,
        pop_thresholds=pop_thresholds,
    )


class SharedMotionRepresentation:
    def __init__(self, parsed: ParsedBVH, normalize_coordinates: bool = True):
        self.parsed = parsed
        self.metadata = parsed.metadata
        self.dt = parsed.metadata.frame_time
        self.frame_count = parsed.metadata.frame_count
        self.timestamps = [round(t * self.dt, 6) for t in range(self.frame_count)]
        self.root_name = parsed.root_node.name
        self.detected_up_axis = detect_coordinate_profile(parsed)
        self.is_normalized = bool(normalize_coordinates and self.detected_up_axis == "Z")
        self.working_up_axis = "Y" if self.is_normalized else self.detected_up_axis

        all_names = [j.name for j in parsed.ordered_joints]
        for j in parsed.ordered_joints:
            for child in j.children:
                if child.is_end_site and child.name not in all_names:
                    all_names.append(child.name)
        self.all_joint_names = all_names

        self.world_positions: Dict[str, List[List[float]]] = {name: [] for name in all_names}
        self.world_rotations: Dict[str, List[List[List[float]]]] = {name: [] for name in all_names}
        self.local_rotations: Dict[str, List[List[List[float]]]] = {name: [] for name in all_names}
        self.root_relative_positions: Dict[str, List[List[float]]] = {name: [] for name in all_names}

        self._compute_forward_kinematics()
        self._compute_root_relative_positions()
        self._compute_derivatives()
        self._compute_com_trajectory()

    def _compute_forward_kinematics(self):
        root = self.parsed.root_node
        is_norm = self.is_normalized

        for frame_idx, frame_motion in enumerate(self.parsed.motion):
            rx, ry, rz = 0.0, 0.0, 0.0
            for ch_name, ch_idx in zip(root.channels, root.channel_indices):
                if ch_name == "Xposition":
                    rx = frame_motion[ch_idx]
                elif ch_name == "Yposition":
                    ry = frame_motion[ch_idx]
                elif ch_name == "Zposition":
                    rz = frame_motion[ch_idx]
            root_local_raw = [root.offset[0] + rx, root.offset[1] + ry, root.offset[2] + rz]
            root_raw_rot = compute_joint_rotation_matrix(root, frame_motion)

            if is_norm:
                root_pos = transform_vector_z_to_y(root_local_raw)
                root_rot = transform_matrix_z_to_y(root_raw_rot)
            else:
                root_pos = root_local_raw
                root_rot = root_raw_rot

            self.world_positions[root.name].append(root_pos)
            self.world_rotations[root.name].append(root_rot)
            self.local_rotations[root.name].append(root_rot)

            def propagate(node: JointNode, p_pos: List[float], p_rot: List[List[float]]):
                for child in node.children:
                    if child.is_end_site:
                        c_off = transform_vector_z_to_y(child.offset) if is_norm else child.offset
                        end_pos = vec_add(p_pos, mat_vec_mul_3x3(p_rot, c_off))
                        self.world_positions[child.name].append(end_pos)
                        self.world_rotations[child.name].append(p_rot)
                        self.local_rotations[child.name].append(identity_matrix_3x3())
                        continue

                    cx, cy, cz = 0.0, 0.0, 0.0
                    for ch_name, ch_idx in zip(child.channels, child.channel_indices):
                        if ch_name == "Xposition":
                            cx = frame_motion[ch_idx]
                        elif ch_name == "Yposition":
                            cy = frame_motion[ch_idx]
                        elif ch_name == "Zposition":
                            cz = frame_motion[ch_idx]
                    c_local_raw = [child.offset[0] + cx, child.offset[1] + cy, child.offset[2] + cz]
                    c_raw_rot = compute_joint_rotation_matrix(child, frame_motion)

                    if is_norm:
                        c_local_pos = transform_vector_z_to_y(c_local_raw)
                        c_local_rot = transform_matrix_z_to_y(c_raw_rot)
                    else:
                        c_local_pos = c_local_raw
                        c_local_rot = c_raw_rot

                    child_pos = vec_add(p_pos, mat_vec_mul_3x3(p_rot, c_local_pos))
                    child_rot = mat_mul_3x3(p_rot, c_local_rot)

                    self.world_positions[child.name].append(child_pos)
                    self.world_rotations[child.name].append(child_rot)
                    self.local_rotations[child.name].append(c_local_rot)

                    propagate(child, child_pos, child_rot)

            propagate(root, root_pos, root_rot)

    def _compute_root_relative_positions(self):
        root_positions = self.world_positions[self.root_name]
        for name in self.all_joint_names:
            pos_list = self.world_positions[name]
            rel_list = []
            for t in range(len(pos_list)):
                rp = root_positions[t]
                p = pos_list[t]
                rel_list.append([p[0] - rp[0], p[1] - rp[1], p[2] - rp[2]])
            self.root_relative_positions[name] = rel_list

    def _compute_derivatives(self):
        dt = self.dt
        fc = self.frame_count
        self.linear_velocities: Dict[str, List[List[float]]] = {name: [] for name in self.all_joint_names}
        self.linear_accelerations: Dict[str, List[List[float]]] = {name: [] for name in self.all_joint_names}
        self.linear_jerks: Dict[str, List[List[float]]] = {name: [] for name in self.all_joint_names}
        self.linear_speeds: Dict[str, List[float]] = {name: [] for name in self.all_joint_names}
        self.angular_velocities: Dict[str, List[float]] = {name: [] for name in self.all_joint_names}
        self.angular_accelerations: Dict[str, List[float]] = {name: [] for name in self.all_joint_names}
        self.angular_jerks: Dict[str, List[float]] = {name: [] for name in self.all_joint_names}

        if fc < 2 or dt <= 0.0:
            for name in self.all_joint_names:
                zeros3 = [[0.0, 0.0, 0.0] for _ in range(fc)]
                zeros1 = [0.0 for _ in range(fc)]
                self.linear_velocities[name] = list(zeros3)
                self.linear_accelerations[name] = list(zeros3)
                self.linear_jerks[name] = list(zeros3)
                self.linear_speeds[name] = list(zeros1)
                self.angular_velocities[name] = list(zeros1)
                self.angular_accelerations[name] = list(zeros1)
                self.angular_jerks[name] = list(zeros1)
            return

        for name in self.all_joint_names:
            pos = self.world_positions[name]
            rot = self.world_rotations[name]
            vels: List[List[float]] = []
            speeds: List[float] = []

            v0 = vec_scale(vec_sub(pos[1], pos[0]), 1.0 / dt)
            vels.append(v0)
            speeds.append(vec_norm(v0))

            for t in range(1, fc):
                v = vec_scale(vec_sub(pos[t], pos[t - 1]), 1.0 / dt)
                vels.append(v)
                speeds.append(vec_norm(v))

            accels: List[List[float]] = []
            dt2 = dt * dt
            for t in range(fc):
                if 1 <= t < fc - 1:
                    a = vec_scale(vec_add(vec_sub(pos[t + 1], vec_scale(pos[t], 2.0)), pos[t - 1]), 1.0 / dt2)
                elif t == 0 and fc > 2:
                    a = vec_scale(vec_add(vec_sub(pos[2], vec_scale(pos[1], 2.0)), pos[0]), 1.0 / dt2)
                elif t == fc - 1 and fc > 2:
                    a = vec_scale(vec_add(vec_sub(pos[fc - 1], vec_scale(pos[fc - 2], 2.0)), pos[fc - 3]), 1.0 / dt2)
                else:
                    a = [0.0, 0.0, 0.0]
                accels.append(a)

            jerks: List[List[float]] = []
            j0 = vec_scale(vec_sub(accels[1], accels[0]), 1.0 / dt) if fc > 1 else [0.0, 0.0, 0.0]
            jerks.append(j0)
            for t in range(1, fc):
                j = vec_scale(vec_sub(accels[t], accels[t - 1]), 1.0 / dt)
                jerks.append(j)

            ang_vel: List[float] = []
            w0 = so3_geodesic_distance(rot[0], rot[1]) / dt if fc > 1 else 0.0
            ang_vel.append(w0)
            for t in range(1, fc):
                w = so3_geodesic_distance(rot[t - 1], rot[t]) / dt
                ang_vel.append(w)

            ang_acc: List[float] = []
            a0 = (ang_vel[1] - ang_vel[0]) / dt if fc > 1 else 0.0
            ang_acc.append(a0)
            for t in range(1, fc):
                aa = (ang_vel[t] - ang_vel[t - 1]) / dt
                ang_acc.append(aa)

            ang_jerk: List[float] = []
            aj0 = (ang_acc[1] - ang_acc[0]) / dt if fc > 1 else 0.0
            ang_jerk.append(aj0)
            for t in range(1, fc):
                aj = (ang_acc[t] - ang_acc[t - 1]) / dt
                ang_jerk.append(aj)

            self.linear_velocities[name] = vels
            self.linear_accelerations[name] = accels
            self.linear_jerks[name] = jerks
            self.linear_speeds[name] = speeds
            self.angular_velocities[name] = ang_vel
            self.angular_accelerations[name] = ang_acc
            self.angular_jerks[name] = ang_jerk

    def _compute_com_trajectory(self):
        self.com_trajectory: List[List[float]] = []
        ordered_names = [j.name for j in self.parsed.ordered_joints]
        n_ordered = len(ordered_names)
        if n_ordered == 0:
            return
        for t in range(self.frame_count):
            cx = sum(self.world_positions[name][t][0] for name in ordered_names) / n_ordered
            cy = sum(self.world_positions[name][t][1] for name in ordered_names) / n_ordered
            cz = sum(self.world_positions[name][t][2] for name in ordered_names) / n_ordered
            self.com_trajectory.append([cx, cy, cz])


def build_shared_motion_representation(
    parsed: ParsedBVH,
    normalize_coordinates: bool = True,
) -> SharedMotionRepresentation:
    return SharedMotionRepresentation(parsed, normalize_coordinates=normalize_coordinates)


def compute_forward_kinematics(
    parsed: ParsedBVH,
) -> Tuple[Dict[str, List[List[float]]], Dict[str, List[List[List[float]]]]]:
    rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)
    return rep.world_positions, rep.world_rotations


def categorize_body_part(joint_name: str, root_name: Optional[str] = None) -> BodyPart:
    if root_name and joint_name.lower() == root_name.lower():
        return BodyPart.PELVIS
    joint_lower = joint_name.lower()
    if any(k in joint_lower for k in ("foot", "toe", "ankle")):
        return BodyPart.FOOT
    if any(k in joint_lower for k in ("leg", "knee", "thigh", "shin", "hip")):
        return BodyPart.PELVIS if "hip" in joint_lower else BodyPart.LEG
    if any(k in joint_lower for k in ("arm", "hand", "finger", "shoulder", "forearm", "wrist", "elbow")):
        return BodyPart.ARM
    if any(k in joint_lower for k in ("head", "neck")):
        return BodyPart.HEAD
    if any(k in joint_lower for k in ("spine", "chest", "torso")):
        return BodyPart.TORSO
    if any(k in joint_lower for k in ("root", "origin", "bip01", "hips", "pelvis")):
        return BodyPart.PELVIS
    return BodyPart.GENERAL


def is_accessory_or_helper_joint(joint_name: str) -> bool:
    lower = joint_name.lower()
    keywords = [
        "helper", "tassel", "brag", "lrag", "tongue", "sword",
        "eye", "collar", "jaw", "mouth", "breast", "fingerbase",
        "inhand", "accessory", "prop", "weapon", "shield", "root_aux"
    ]
    return any(k in lower for k in keywords)


def assess_multiaxial_impact(
    family: str,
    joint_name: str,
    measured_metric: float,
    threshold: float,
    physical_disp: float,
    frame_span: int,
    dt: float,
    skeleton_scale: float,
    has_context: bool = True,
    is_helper_joint: Optional[bool] = None,
    is_ground_supported: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Tuple[AssessmentVerdict, Severity, float, Dict[str, Any]]:
    if is_helper_joint is None:
        is_helper_joint = is_accessory_or_helper_joint(joint_name)

    safe_thresh = max(threshold, 1e-6)
    safe_scale = max(skeleton_scale, 1e-6)
    num_ratio = measured_metric / safe_thresh
    disp_visible = max(2.5, skeleton_scale * 0.02)
    disp_review = max(0.8, skeleton_scale * 0.006)
    disp_noise = max(0.3, skeleton_scale * 0.0025)
    duration_sec = frame_span * dt

    dur_category = "single_frame" if frame_span == 1 else ("transient" if frame_span <= 3 else "sustained")

    multi_axial_details: Dict[str, Any] = {
        "numerical_abnormality": {
            "measured": round(measured_metric, 4),
            "threshold": round(threshold, 4),
            "ratio": round(num_ratio, 4),
        },
        "physical_displacement": {
            "displacement": round(physical_disp, 4),
            "scale": round(skeleton_scale, 4),
            "scale_ratio": round(physical_disp / safe_scale, 4),
            "disp_visible_threshold": round(disp_visible, 4),
            "disp_review_threshold": round(disp_review, 4),
            "disp_noise_threshold": round(disp_noise, 4),
        },
        "duration": {
            "frames": frame_span,
            "duration_seconds": round(duration_sec, 4),
            "category": dur_category,
        },
        "contextual_reliability": {
            "has_context": has_context,
            "is_helper_joint": is_helper_joint,
            "is_ground_supported": is_ground_supported,
            "scale_valid": (skeleton_scale > 0.0 and math.isfinite(skeleton_scale)),
        },
    }
    if extra_context:
        multi_axial_details["contextual_reliability"].update(extra_context)

    if not has_context or skeleton_scale <= 0.0 or not math.isfinite(skeleton_scale):
        return AssessmentVerdict.INCONCLUSIVE, Severity.LOW, 0.40, multi_axial_details

    if is_helper_joint and physical_disp < disp_visible:
        return AssessmentVerdict.NUMERICAL_ONLY, Severity.LOW, 0.50, multi_axial_details

    if physical_disp < disp_noise and num_ratio < 2.0:
        return AssessmentVerdict.NUMERICAL_ONLY, Severity.LOW, 0.50, multi_axial_details

    if num_ratio >= 1.5 and physical_disp >= disp_visible:
        sev = Severity.CRITICAL if (num_ratio >= 2.5 or physical_disp >= skeleton_scale * 0.05) else Severity.HIGH
        conf = min(0.98, 0.85 + 0.05 * min(num_ratio - 1.5, 2.0))
        return AssessmentVerdict.LIKELY_VISIBLE_DEFECT, sev, round(conf, 4), multi_axial_details

    if num_ratio >= 1.0 and physical_disp >= disp_review:
        return AssessmentVerdict.REVIEW, Severity.MEDIUM, 0.75, multi_axial_details

    return AssessmentVerdict.NUMERICAL_ONLY, Severity.LOW, 0.50, multi_axial_details


def detect_series_jitter(
    series: List[float],
    dt: float,
    min_accel: float,
    min_amp: float = 0.0,
    min_flips: int = 1,
    min_reversals: int = 1,
    min_sar: float = 0.0,
    is_angular: bool = True,
    shared_stats: Optional[Tuple[float, float]] = None,
) -> Tuple[List[Tuple[int, int]], Dict[int, float], float, float]:
    if len(series) < 3 or dt <= 0.0:
        return [], {}, min_accel, 0.0
    dt2 = dt * dt
    n = len(series)
    accelerations: List[float] = []
    frame_accel: Dict[int, float] = {}
    d2_vals: Dict[int, float] = {}
    for t in range(1, n - 1):
        if is_angular:
            diff1 = (series[t] - series[t - 1] + 180.0) % 360.0 - 180.0
            diff2 = (series[t + 1] - series[t] + 180.0) % 360.0 - 180.0
        else:
            diff1 = series[t] - series[t - 1]
            diff2 = series[t + 1] - series[t]
        d2 = diff2 - diff1
        acc = d2 / dt2
        accelerations.append(acc)
        frame_accel[t] = acc
        d2_vals[t] = d2
    if shared_stats is not None:
        threshold, mad_acc = shared_stats
    else:
        med_acc = calc_median(accelerations)
        mad_acc = calc_mad(accelerations, med_acc)
        threshold = max(4.0 * mad_acc, min_accel)
    flagged_frames: List[int] = []
    frame_evidence: Dict[int, float] = {}
    start_t = 2 if n > 3 and min_amp > 0.0 else 1
    for t in range(start_t, n - 1):
        a_curr = frame_accel[t]
        if abs(a_curr) > threshold and (abs(d2_vals[t]) >= min_amp * 0.7 if min_amp > 0.0 else True):
            flagged_frames.append(t)
            frame_evidence[t] = abs(a_curr)
    raw_intervals = merge_frame_intervals(flagged_frames, max_gap=2)
    if min_amp <= 0.0 and min_flips <= 1 and min_reversals <= 1:
        return raw_intervals, frame_evidence, threshold, mad_acc

    min_span_len = 4 if min_reversals >= 3 else 3
    intervals: List[Tuple[int, int]] = []
    for s_idx, e_idx in raw_intervals:
        span = list(range(s_idx, e_idx + 1))
        if len(span) < min_span_len:
            continue
        flips = 0
        for t in range(s_idx, e_idx):
            if t in d2_vals and (t + 1) in d2_vals:
                if d2_vals[t] * d2_vals[t + 1] < 0:
                    flips += 1
        sub_series = [series[t] for t in range(max(1, s_idx - 1), min(n, e_idx + 2))]
        p2p = max(sub_series) - min(sub_series)

        deltas = []
        for t in range(max(1, s_idx), min(n, e_idx + 2)):
            if is_angular:
                d = (series[t] - series[t - 1] + 180.0) % 360.0 - 180.0
            else:
                d = series[t] - series[t - 1]
            deltas.append(d)
        reversals = 0
        min_step = 5.0 if min_amp >= 20.0 else (2.0 if min_amp >= 10.0 else (min_amp * 0.1 if min_amp > 0.0 else 0.5))
        for i in range(len(deltas) - 1):
            if deltas[i] * deltas[i + 1] < 0 and (abs(deltas[i]) >= min_step or abs(deltas[i + 1]) >= min_step):
                reversals += 1
        sar = reversals / max(1, len(deltas) - 1)

        if flips >= min_flips and p2p >= min_amp and reversals >= min_reversals and sar >= min_sar:
            intervals.append((s_idx, e_idx))
    return intervals, frame_evidence, threshold, mad_acc


def generate_finding_id(
    anomaly_type: AnomalyType,
    affected_joint: str,
    frame_start: int,
    frame_end: int,
    evidence: Dict[str, Any],
) -> str:
    ev_canonical = json.dumps(evidence, sort_keys=True)
    raw = f"{anomaly_type.value}:{affected_joint}:{frame_start}:{frame_end}:{ev_canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_analysis_hash(
    content_hash: str,
    skeleton_signature: str,
    parser_version: str,
    detector_version: str,
    findings: List[Finding],
) -> str:
    sorted_findings = sorted(
        findings,
        key=lambda f: (f.anomaly_type.value, f.affected_joint, f.frame_start, f.frame_end),
    )
    findings_data = [
        {
            "finding_id": f.finding_id,
            "anomaly_type": f.anomaly_type.value,
            "affected_joint": f.affected_joint,
            "frame_start": f.frame_start,
            "frame_end": f.frame_end,
            "evidence": f.evidence if isinstance(f.evidence, dict) else (f.evidence.model_dump() if hasattr(f.evidence, "model_dump") else dict(f.evidence)),
        }
        for f in sorted_findings
    ]
    payload = {
        "content_hash": content_hash,
        "skeleton_signature": skeleton_signature,
        "parser_version": parser_version,
        "detector_version": detector_version,
        "findings": findings_data,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def merge_boundary_findings(findings: List[Finding], dt: float) -> List[Finding]:
    if not findings:
        return []
    severity_order = {
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }
    verdict_priority = {
        AssessmentVerdict.INCONCLUSIVE: 1,
        AssessmentVerdict.NUMERICAL_ONLY: 2,
        AssessmentVerdict.REVIEW: 3,
        AssessmentVerdict.LIKELY_VISIBLE_DEFECT: 4,
    }

    findings_by_group: Dict[Tuple[str, str], List[Finding]] = {}
    for f in findings:
        key = (f.affected_joint, str(f.anomaly_type.value if hasattr(f.anomaly_type, "value") else f.anomaly_type))
        findings_by_group.setdefault(key, []).append(f)

    merged_findings: List[Finding] = []
    for key, group in findings_by_group.items():
        group.sort(key=lambda x: (x.frame_start, x.frame_end, x.finding_id))
        current = group[0]
        for nxt in group[1:]:
            if nxt.frame_start == current.frame_start and nxt.frame_end == current.frame_end:
                if (nxt.confidence or 0.0) > (current.confidence or 0.0):
                    current = nxt
                continue
            if nxt.frame_start <= current.frame_end + 2:
                new_start = min(current.frame_start, nxt.frame_start)
                new_end = max(current.frame_end, nxt.frame_end)
                cur_sev = severity_order.get(current.severity, 0)
                nxt_sev = severity_order.get(nxt.severity, 0)
                new_sev = current.severity if cur_sev >= nxt_sev else nxt.severity
                new_conf = max(current.confidence or 0.0, nxt.confidence or 0.0)
                cur_verd = verdict_priority.get(current.verdict, 0)
                nxt_verd = verdict_priority.get(nxt.verdict, 0)
                new_verdict = current.verdict if cur_verd >= nxt_verd else nxt.verdict
                merged_ev = copy.deepcopy(current.evidence if cur_sev >= nxt_sev else nxt.evidence)
                cur_val = current.evidence.get("measured_value")
                nxt_val = nxt.evidence.get("measured_value")
                if isinstance(cur_val, (int, float)) and isinstance(nxt_val, (int, float)):
                    merged_ev["measured_value"] = max(cur_val, nxt_val)
                new_exp = current.explanation if cur_sev >= nxt_sev else nxt.explanation
                fid = generate_finding_id(current.anomaly_type, current.affected_joint, new_start, new_end, merged_ev)
                current = Finding(
                    finding_id=fid,
                    affected_joint=current.affected_joint,
                    affected_body_part=current.affected_body_part,
                    frame_start=new_start,
                    frame_end=new_end,
                    time_start=round(min(current.time_start, nxt.time_start), 6),
                    time_end=round(max(current.time_end, nxt.time_end), 6),
                    anomaly_type=current.anomaly_type,
                    severity=new_sev,
                    confidence=new_conf,
                    verdict=new_verdict,
                    evidence=merged_ev,
                    detector_version=current.detector_version,
                    explanation=new_exp,
                    created_at=current.created_at,
                )
            else:
                merged_findings.append(current)
                current = nxt
        merged_findings.append(current)
    merged_findings.sort(key=lambda f: (f.frame_start, f.frame_end, f.affected_joint, f.finding_id))
    return merged_findings
def detect_root_discontinuity(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    root = parsed.root_node
    dt = metadata.frame_time
    skeleton_height = metadata.skeleton_scale
    if skeleton_height <= 0.0 or not math.isfinite(skeleton_height):
        return findings

    trans_indices: List[int] = []
    for ch_name, ch_idx in zip(root.channels, root.channel_indices):
        if "position" in ch_name.lower():
            trans_indices.append(ch_idx)

    if len(trans_indices) >= 3 and metadata.frame_count >= 3:
        speeds: List[float] = []
        for t in range(1, metadata.frame_count):
            prev_m = parsed.motion[t - 1]
            curr_m = parsed.motion[t]
            dx = curr_m[trans_indices[0]] - prev_m[trans_indices[0]]
            dy = curr_m[trans_indices[1]] - prev_m[trans_indices[1]]
            dz = curr_m[trans_indices[2]] - prev_m[trans_indices[2]]
            disp = math.sqrt(dx * dx + dy * dy + dz * dz)
            speeds.append(disp / dt)

        if whole_clip_stats is not None:
            threshold = whole_clip_stats.root_trans_threshold
        else:
            median_speed = calc_median(speeds)
            threshold = max(5.0 * median_speed, skeleton_height * 2.0)

        flagged_frames: List[int] = []
        frame_evidence: Dict[int, float] = {}
        for idx, spd in enumerate(speeds):
            t = idx + 1
            if spd > threshold:
                flagged_frames.append(t)
                frame_evidence[t] = spd

        intervals = merge_frame_intervals(flagged_frames, max_gap=2)
        for start, end in intervals:
            f_start = start
            f_end = min(metadata.frame_count - 1, end + 1)
            max_spd = max(frame_evidence[f] for f in range(start, end + 1) if f in frame_evidence)
            peak_f = max(range(start, end + 1), key=lambda f: frame_evidence.get(f, 0.0))
            evidence = {
                "metric_name": "root_translation_speed",
                "measured_value": round(max_spd, 4),
                "max_speed": round(max_spd, 4),
                "threshold": round(threshold, 4),
                "unit": "units_per_sec",
                "peak_frame": peak_f,
                "display_peak_frame": peak_f + 1,
            }
            fid = generate_finding_id(
                AnomalyType.ROOT_DISCONTINUITY, root.name, f_start, f_end, evidence
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=root.name,
                    affected_body_part=categorize_body_part(root.name, root_name=root.name),
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(f_start * dt, 6),
                    time_end=round(f_end * dt, 6),
                    anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
                    severity=Severity.HIGH,
                    confidence=0.95,
                    verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Abrupt root translation jump of {max_spd:.1f} units/s exceeding 5x median baseline ({threshold:.1f} units/s)",
                )
            )

    rot_indices = [
        ch_idx for ch_name, ch_idx in zip(root.channels, root.channel_indices)
        if "rotation" in ch_name.lower()
    ]
    if len(rot_indices) >= 3 and metadata.frame_count >= 5:
        rot_speeds: List[float] = []
        for t in range(1, metadata.frame_count):
            r_prev = compute_joint_rotation_matrix(root, parsed.motion[t - 1])
            r_curr = compute_joint_rotation_matrix(root, parsed.motion[t])
            d = so3_geodesic_distance(r_prev, r_curr)
            rot_speeds.append(d / dt)

        if whole_clip_stats is not None:
            ang_threshold = whole_clip_stats.root_rot_threshold
        else:
            med_w = calc_median(rot_speeds[1:]) if len(rot_speeds) > 1 else 0.0
            mad_w = calc_mad(rot_speeds[1:], med_w) if len(rot_speeds) > 1 else 0.0
            ang_threshold = max(450.0, med_w + 6.0 * max(mad_w, 5.0))

        flagged_rot: List[int] = [
            t for idx, w in enumerate(rot_speeds)
            if (t := idx + 1) >= 2 and w > 200.0
        ]
        rot_intervals = merge_frame_intervals(flagged_rot, max_gap=1)
        for s, e in rot_intervals:
            span_len = e - s + 1
            if span_len >= 3 and any(rot_speeds[t - 1] > ang_threshold for t in range(s, e + 1)):
                max_w = max(rot_speeds[t - 1] for t in range(s, e + 1) if t - 1 < len(rot_speeds))
                peak_f = max(range(s, e + 1), key=lambda t: rot_speeds[t - 1] if t - 1 < len(rot_speeds) else 0.0)
                evidence = {
                    "metric_name": "root_angular_discontinuity",
                    "measured_value": round(max_w, 4),
                    "threshold": round(ang_threshold, 4),
                    "unit": "deg_per_sec",
                    "peak_frame": peak_f,
                    "display_peak_frame": peak_f + 1,
                }
                fid = generate_finding_id(
                    AnomalyType.ROOT_DISCONTINUITY, root.name, s, e, evidence
                )
                findings.append(
                    Finding(
                        finding_id=fid,
                        affected_joint=root.name,
                        affected_body_part=categorize_body_part(root.name, root_name=root.name),
                        frame_start=s,
                        frame_end=e,
                        time_start=round(s * dt, 6),
                        time_end=round(e * dt, 6),
                        anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
                        severity=Severity.HIGH if max_w > ang_threshold * 1.5 else Severity.MEDIUM,
                        confidence=0.95,
                        evidence=evidence,
                        detector_version=DETECTOR_VERSION,
                        explanation=f"Root rotational discontinuity: peak angular speed {max_w:.1f} deg/s exceeds threshold of {ang_threshold:.1f} deg/s.",
                        verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                        peak_frame=peak_f,
                        display_peak_frame=peak_f + 1,
                    )
                )

    return findings


def create_jitter_findings(
    spec: JitterFindingSpec,
    intervals: List[Tuple[int, int]],
    frame_evidence: Dict[int, float],
) -> List[Finding]:
    findings: List[Finding] = []
    for start, end in intervals:
        f_start = start + 1
        f_end = end + 1
        peak_acc = max(frame_evidence[f] for f in range(start, end + 1) if f in frame_evidence)
        evidence: Dict[str, Any] = {
            "channel": spec.channel_name,
            "peak_acceleration": f"{peak_acc:.6f}",
            "threshold": f"{spec.threshold:.6f}",
            "unit": spec.unit,
        }
        if spec.mad_acc is not None:
            evidence["mad"] = f"{spec.mad_acc:.6f}"
        fid = generate_finding_id(spec.anomaly_type, spec.joint_name, f_start, f_end, evidence)
        sev = Severity.HIGH if peak_acc > spec.threshold * 2.0 else Severity.MEDIUM
        explanation = (
            f"High-frequency rotational jitter on {spec.joint_name} {spec.channel_name} with acceleration of {peak_acc:.1f} deg/s^2."
            if spec.anomaly_type == AnomalyType.ROTATION_JITTER
            else f"Translational jitter on root translation {spec.channel_name} with acceleration {peak_acc:.2f} units/s^2."
        )
        findings.append(
            Finding(
                finding_id=fid,
                affected_joint=spec.joint_name,
                affected_body_part=spec.body_part,
                frame_start=f_start,
                frame_end=f_end,
                time_start=round(start * spec.dt, 6),
                time_end=round(end * spec.dt, 6),
                anomaly_type=spec.anomaly_type,
                severity=sev,
                confidence=0.90 if spec.anomaly_type == AnomalyType.ROTATION_JITTER else 0.88,
                evidence=evidence,
                detector_version=DETECTOR_VERSION,
                explanation=explanation,
            )
        )
    return findings


def detect_rotation_jitter(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    if metadata.frame_count < 5:
        return findings

    min_rot_accel = 20000.0

    for joint in parsed.ordered_joints:
        rot_ch_indices = [
            (ch_name, ch_idx)
            for ch_name, ch_idx in zip(joint.channels, joint.channel_indices)
            if "rotation" in ch_name.lower()
        ]
        if not rot_ch_indices:
            continue

        for ch_name, ch_idx in rot_ch_indices:
            raw_angles = [parsed.motion[t][ch_idx] for t in range(metadata.frame_count)]
            unwrapped = unwrap_angles(raw_angles)
            shared = whole_clip_stats.jitter_thresholds.get(f"{joint.name}:{ch_name}") if whole_clip_stats else None
            intervals, frame_evidence, threshold, mad_acc = detect_series_jitter(
                unwrapped, dt, min_rot_accel, min_amp=25.0, min_flips=2, min_reversals=3, min_sar=0.50, shared_stats=shared
            )
            spec = JitterFindingSpec(
                joint_name=joint.name,
                body_part=categorize_body_part(joint.name),
                anomaly_type=AnomalyType.ROTATION_JITTER,
                channel_name=ch_name,
                threshold=threshold,
                dt=dt,
                unit="deg_per_sec_sq",
                mad_acc=mad_acc,
            )
            findings.extend(
                create_jitter_findings(
                    spec,
                    intervals,
                    frame_evidence,
                )
            )
    return findings


def detect_translation_jitter(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    root = parsed.root_node
    dt = metadata.frame_time
    skeleton_height = metadata.skeleton_scale
    if metadata.frame_count < 5 or skeleton_height <= 0.0 or not math.isfinite(skeleton_height):
        return findings

    min_trans_accel = skeleton_height * 15.0
    min_trans_amp = skeleton_height * 0.08

    target_joints = [
        j for j in parsed.ordered_joints
        if any("position" in ch.lower() for ch in j.channels)
    ]
    if not target_joints and root not in target_joints:
        target_joints = [root]

    for joint in target_joints:
        trans_ch_indices = [
            (ch_name, ch_idx)
            for ch_name, ch_idx in zip(joint.channels, joint.channel_indices)
            if "position" in ch_name.lower()
        ]
        b_part = categorize_body_part(joint.name, root_name=root.name)
        for ch_name, ch_idx in trans_ch_indices:
            raw_vals = [parsed.motion[t][ch_idx] for t in range(metadata.frame_count)]
            shared = whole_clip_stats.jitter_thresholds.get(f"{joint.name}:{ch_name}") if whole_clip_stats else None
            intervals, frame_evidence, threshold, mad_acc = detect_series_jitter(
                raw_vals, dt, min_trans_accel, min_amp=min_trans_amp, min_flips=2, min_reversals=2, min_sar=0.40, is_angular=False, shared_stats=shared
            )
            spec = JitterFindingSpec(
                joint_name=joint.name,
                body_part=b_part,
                anomaly_type=AnomalyType.TRANSLATION_JITTER,
                channel_name=ch_name,
                threshold=threshold,
                dt=dt,
                unit="units_per_sec_sq",
                mad_acc=mad_acc,
            )
            findings.extend(
                create_jitter_findings(
                    spec,
                    intervals,
                    frame_evidence,
                )
            )
    return findings


def detect_foot_sliding(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    joint_positions: Dict[str, List[List[float]]],
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> Tuple[List[Finding], bool]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    skeleton_height = metadata.skeleton_scale
    if skeleton_height <= 0.0 or not math.isfinite(skeleton_height) or metadata.frame_count < 4:
        return findings, False

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_joints: List[str] = []
    for j in parsed.ordered_joints:
        norm = j.name.lower().replace(" ", "").replace("_", "")
        if norm in candidate_foot_names:
            foot_joints.append(j.name)

    if not foot_joints:
        return findings, False

    if whole_clip_stats is not None:
        floor_y = whole_clip_stats.floor_y_p20
    else:
        all_foot_y: List[float] = []
        for fj in foot_joints:
            all_foot_y.extend(p[1] for p in joint_positions.get(fj, []))
        if all_foot_y:
            sorted_foot_y = sorted(all_foot_y)
            floor_y = sorted_foot_y[max(0, int(len(sorted_foot_y) * 0.20))]
        else:
            floor_y = 0.0

    contact_vert_speed_thresh = skeleton_height * 0.08
    horizontal_drift_speed_threshold = skeleton_height * 0.35

    for foot_joint in foot_joints:
        positions = joint_positions[foot_joint]
        n_frames = len(positions)
        if n_frames < 4:
            continue

        ys = [p[1] for p in positions[1:]] if n_frames > 2 else [p[1] for p in positions]
        if not ys:
            continue
        joint_floor_y = min(ys)
        contact_height_thresh = max(floor_y + skeleton_height * 0.02, joint_floor_y + skeleton_height * 0.012)

        in_contact_frames: List[int] = []
        for t in range(1, n_frames):
            prev_p = positions[t - 1]
            curr_p = positions[t]
            curr_y = curr_p[1]
            v_y = abs(curr_y - prev_p[1]) / dt

            if (curr_y <= contact_height_thresh) and (v_y <= contact_vert_speed_thresh):
                in_contact_frames.append(t)

        contact_intervals: List[Tuple[int, int]] = []
        if in_contact_frames:
            cs = in_contact_frames[0]
            ce = in_contact_frames[0]
            for cf in in_contact_frames[1:]:
                if cf <= ce + 2:
                    ce = cf
                else:
                    contact_intervals.append((cs, ce))
                    cs = cf
                    ce = cf
            contact_intervals.append((cs, ce))

        flagged_frames: List[int] = []
        frame_evidence: Dict[int, float] = {}

        for cs, ce in contact_intervals:
            duration = (ce - cs + 1) * dt
            if duration < 0.08:
                continue

            stance_drift = 0.0
            slide_frames: List[int] = []
            for t in range(cs, ce + 1):
                prev_p = positions[t - 1]
                curr_p = positions[t]
                dx = curr_p[0] - prev_p[0]
                dz = curr_p[2] - prev_p[2]
                disp = math.sqrt(dx * dx + dz * dz)
                stance_drift += disp
                h_speed = disp / dt

                if h_speed > horizontal_drift_speed_threshold:
                    slide_frames.append(t)
                    frame_evidence[t] = h_speed

            if slide_frames and stance_drift >= skeleton_height * 0.08:
                flagged_frames.extend(slide_frames)

        intervals = merge_frame_intervals(flagged_frames, max_gap=2)
        for start, end in intervals:
            f_start = start
            f_end = end
            max_drift_spd = max(frame_evidence[f] for f in range(start, end + 1) if f in frame_evidence)
            peak_f = max(range(start, end + 1), key=lambda f: frame_evidence.get(f, 0.0))
            evidence = {
                "max_drift_speed": f"{max_drift_spd:.6f}",
                "threshold": f"{horizontal_drift_speed_threshold:.6f}",
                "unit": "units_per_sec",
                "peak_frame": peak_f,
                "display_peak_frame": peak_f + 1,
            }
            fid = generate_finding_id(
                AnomalyType.PLANTED_FOOT_SLIDING, foot_joint, f_start, f_end, evidence
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=foot_joint,
                    affected_body_part=BodyPart.FOOT,
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(start * dt, 6),
                    time_end=round(end * dt, 6),
                    anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
                    severity=Severity.HIGH if max_drift_spd > horizontal_drift_speed_threshold * 1.8 else Severity.MEDIUM,
                    confidence=0.92,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Planted foot sliding detected on {foot_joint} with drift speed of {max_drift_spd:.2f} units/s while in contact.",
                    verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                    peak_frame=peak_f,
                    display_peak_frame=peak_f + 1,
                )
            )

    return findings, True


def detect_sensor_tracking_artifacts(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    joint_positions: Dict[str, List[List[float]]],
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    scale = metadata.skeleton_scale
    if metadata.frame_count < 5 or scale <= 0.0 or not math.isfinite(scale):
        return findings

    root_pos = joint_positions.get(parsed.root_node.name, [])
    if whole_clip_stats is not None:
        root_moves = whole_clip_stats.root_moves
    else:
        root_moves = False
        if len(root_pos) >= 2:
            root_disp = sum(
                vec_dist(root_pos[t], root_pos[t - 1]) for t in range(1, len(root_pos))
            )
            if root_disp > scale * 0.05:
                root_moves = True

    raw_flatlines: List[Tuple[JointNode, int, int, int]] = []
    frame_frozen_counts: Dict[int, int] = {}
    for joint in parsed.ordered_joints:
        if joint.name == parsed.root_node.name:
            continue

        positions = joint_positions.get(joint.name, [])
        flat_frames: List[int] = []
        if len(positions) >= 4:
            total_joint_disp = sum(
                vec_dist(positions[t], positions[t - 1]) for t in range(1, len(positions))
            )
            if total_joint_disp > scale * 0.05:
                for t in range(1, len(positions)):
                    disp = vec_dist(positions[t], positions[t - 1])
                    if disp < 1e-5:
                        flat_frames.append(t)

        rot_ch_indices = [
            ch_idx
            for ch_name, ch_idx in zip(joint.channels, joint.channel_indices)
            if "rotation" in ch_name.lower()
        ]
        if rot_ch_indices:
            if whole_clip_stats is not None:
                max_rot_diff = max(whole_clip_stats.channel_max_rot_diff.get(idx, 0.0) for idx in rot_ch_indices)
            else:
                max_rot_diff = max(
                    max(parsed.motion[t][idx] for t in range(metadata.frame_count))
                    - min(parsed.motion[t][idx] for t in range(metadata.frame_count))
                    for idx in rot_ch_indices
                )
            if max_rot_diff > 3.0:
                for t in range(1, metadata.frame_count):
                    ch_diff = sum(
                        abs((parsed.motion[t][idx] - parsed.motion[t - 1][idx] + 180.0) % 360.0 - 180.0)
                        for idx in rot_ch_indices
                    )
                    if ch_diff < 1e-5:
                        flat_frames.append(t)

        intervals = merge_frame_intervals(flat_frames, max_gap=1)
        for s, e in intervals:
            span_len = e - s + 1
            if span_len >= 3 and (span_len * dt) >= 0.08 and span_len < metadata.frame_count - 2:
                raw_flatlines.append((joint, s, e, span_len))
                for f in range(s, e + 1):
                    frame_frozen_counts[f] = frame_frozen_counts.get(f, 0) + 1

    for joint, s, e, span_len in raw_flatlines:
        f_start = s + 1
        f_end = e + 1
        is_helper = is_accessory_or_helper_joint(joint.name)
        positions = joint_positions.get(joint.name, [])
        root_disp_span = 0.0
        if root_pos and len(root_pos) > e:
            root_disp_span = sum(
                vec_dist(root_pos[t], root_pos[t - 1]) for t in range(s, e + 1)
            )
        active_pre = False
        if s >= 3 and len(positions) > s:
            pre_disp = sum(
                vec_dist(positions[t], positions[t - 1]) for t in range(max(1, s - 5), s)
            )
            if pre_disp > scale * 0.01:
                active_pre = True

        is_static_rest = (s <= 2 or not active_pre) and (root_disp_span < scale * 0.02)
        is_global_freeze = max((frame_frozen_counts.get(f, 0) for f in range(s, e + 1)), default=0) >= 8

        if is_helper or is_static_rest or is_global_freeze:
            verdict = AssessmentVerdict.NUMERICAL_ONLY
            sev = Severity.LOW
            conf = 0.50
        else:
            verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
            sev = Severity.HIGH
            conf = 0.92

        evidence = {
            "duration_seconds": f"{span_len * dt:.4f}",
            "frames_frozen": span_len,
            "variance": "0.000000",
            "is_helper_joint": is_helper,
            "is_static_rest": is_static_rest,
            "is_global_freeze": is_global_freeze,
        }
        fid = generate_finding_id(
            AnomalyType.OPTICAL_OCCLUSION_FLATLINE,
            joint.name,
            f_start,
            f_end,
            evidence,
        )
        findings.append(
            Finding(
                finding_id=fid,
                affected_joint=joint.name,
                affected_body_part=categorize_body_part(joint.name),
                frame_start=f_start,
                frame_end=f_end,
                time_start=round(s * dt, 6),
                time_end=round(e * dt, 6),
                anomaly_type=AnomalyType.OPTICAL_OCCLUSION_FLATLINE,
                severity=sev,
                confidence=conf,
                evidence=evidence,
                detector_version=DETECTOR_VERSION,
                explanation=f"Optical marker occlusion flatline detected on {joint.name} for {span_len} consecutive frames.",
                verdict=verdict,
            )
        )

    pairs: List[Tuple[str, str]] = []
    joint_names = [j.name for j in parsed.ordered_joints]
    for name in joint_names:
        lower = name.lower()
        if "left" in lower:
            counterpart = name.replace("Left", "Right").replace("left", "right")
            if counterpart in joint_names and (name, counterpart) not in pairs:
                pairs.append((name, counterpart))

    for left_name, right_name in pairs:
        l_pos = joint_positions.get(left_name, [])
        r_pos = joint_positions.get(right_name, [])
        if len(l_pos) != len(r_pos) or len(l_pos) < 5:
            continue

        swap_frames: List[int] = []
        for t in range(1, len(l_pos)):
            l_prev = l_pos[t - 1]
            r_prev = r_pos[t - 1]
            l_curr = l_pos[t]
            r_curr = r_pos[t]

            swap_dist = vec_dist(l_curr, r_prev) + vec_dist(r_curr, l_prev)
            self_dist = vec_dist(l_curr, l_prev) + vec_dist(r_curr, r_prev)
            if swap_dist < self_dist * 0.35 and self_dist > scale * 0.12:
                swap_frames.append(t)

        intervals = merge_frame_intervals(swap_frames, max_gap=2)
        for s, e in intervals:
            f_start = s + 1
            f_end = e + 1
            evidence = {
                "pair": [left_name, right_name],
                "left_x": f"{l_pos[s][0]:.4f}",
                "right_x": f"{r_pos[s][0]:.4f}",
            }
            fid = generate_finding_id(
                AnomalyType.OPTICAL_MARKER_SWAP,
                left_name,
                f_start,
                f_end,
                evidence,
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=left_name,
                    affected_body_part=categorize_body_part(left_name),
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(s * dt, 6),
                    time_end=round(e * dt, 6),
                    anomaly_type=AnomalyType.OPTICAL_MARKER_SWAP,
                    severity=Severity.CRITICAL,
                    confidence=0.95,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Bilateral optical marker swap detected between {left_name} and {right_name}.",
                )
            )

    return findings


def detect_representation_singularities(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    if metadata.frame_count < 3:
        return findings

    for joint in parsed.ordered_joints:
        rot_channels = [
            (ch_name, ch_idx)
            for ch_name, ch_idx in zip(joint.channels, joint.channel_indices)
            if "rotation" in ch_name.lower()
        ]
        if len(rot_channels) != 3:
            continue

        mid_ch_name, mid_ch_idx = rot_channels[1]
        ch0_name, ch0_idx = rot_channels[0]
        ch2_name, ch2_idx = rot_channels[2]

        flagged_frames: List[int] = []
        frame_evidence: Dict[int, Dict[str, float]] = {}

        for t in range(1, metadata.frame_count):
            mid_val = parsed.motion[t][mid_ch_idx]
            mid_rad = math.radians(mid_val)
            cos_mid = math.cos(mid_rad)

            if abs(cos_mid) < 0.18:
                d0 = abs((parsed.motion[t][ch0_idx] - parsed.motion[t - 1][ch0_idx] + 180.0) % 360.0 - 180.0)
                d2 = abs((parsed.motion[t][ch2_idx] - parsed.motion[t - 1][ch2_idx] + 180.0) % 360.0 - 180.0)

                if d0 > 40.0 and d2 > 40.0:
                    r_curr = compute_joint_rotation_matrix(joint, parsed.motion[t])
                    r_prev = compute_joint_rotation_matrix(joint, parsed.motion[t - 1])
                    r_prev_t = [
                        [r_prev[0][0], r_prev[1][0], r_prev[2][0]],
                        [r_prev[0][1], r_prev[1][1], r_prev[2][1]],
                        [r_prev[0][2], r_prev[1][2], r_prev[2][2]],
                    ]
                    r_rel = mat_mul_3x3(r_curr, r_prev_t)
                    tr = r_rel[0][0] + r_rel[1][1] + r_rel[2][2]
                    cos_phi = clamp_val((tr - 1.0) / 2.0, -1.0, 1.0)
                    geodesic_deg = math.degrees(math.acos(cos_phi))

                    if geodesic_deg < 20.0:
                        flagged_frames.append(t)
                        frame_evidence[t] = {
                            "middle_angle": mid_val,
                            "euler_jump": max(d0, d2),
                            "geodesic_angle": geodesic_deg,
                        }

        intervals = merge_frame_intervals(flagged_frames, max_gap=2)
        for s, e in intervals:
            f_start = s + 1
            f_end = e + 1
            max_jump = max(frame_evidence[f]["euler_jump"] for f in range(s, e + 1) if f in frame_evidence)
            min_geo = min(frame_evidence[f]["geodesic_angle"] for f in range(s, e + 1) if f in frame_evidence)
            evidence = {
                "middle_channel": mid_ch_name,
                "euler_jump_degrees": f"{max_jump:.2f}",
                "geodesic_so3_change": f"{min_geo:.2f}",
            }
            fid = generate_finding_id(
                AnomalyType.EULER_GIMBAL_LOCK_FLIP,
                joint.name,
                f_start,
                f_end,
                evidence,
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=joint.name,
                    affected_body_part=categorize_body_part(joint.name),
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(s * dt, 6),
                    time_end=round(e * dt, 6),
                    anomaly_type=AnomalyType.EULER_GIMBAL_LOCK_FLIP,
                    severity=Severity.HIGH,
                    confidence=0.96,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Euler gimbal lock flip singularity on {joint.name}: Euler coordinate jump of {max_jump:.1f} deg while 3D geodesic rotation changed only {min_geo:.1f} deg.",
                )
            )

    return findings


def detect_biomechanical_violations(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    joint_positions: Dict[str, List[List[float]]],
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    scale = metadata.skeleton_scale
    if metadata.frame_count < 2 or scale <= 0.0 or not math.isfinite(scale):
        return findings

    for child in parsed.ordered_joints:
        if not child.parent_name or child.parent_name not in parsed.joint_map:
            continue
        parent = parsed.joint_map[child.parent_name]

        rest_len = vec_norm(child.offset)
        if rest_len < scale * 0.02:
            continue

        c_pos = joint_positions.get(child.name, [])
        p_pos = joint_positions.get(parent.name, [])
        if len(c_pos) != len(p_pos) or not c_pos:
            continue

        len_flagged: List[int] = []
        max_devs: Dict[int, float] = {}
        for t in range(len(c_pos)):
            curr_len = vec_dist(c_pos[t], p_pos[t])
            dev = abs(curr_len - rest_len) / rest_len
            if dev > 0.025:
                len_flagged.append(t)
                max_devs[t] = dev

        intervals = merge_frame_intervals(len_flagged, max_gap=2)
        for s, e in intervals:
            f_start = s + 1
            f_end = e + 1
            peak_dev = max(max_devs[f] for f in range(s, e + 1) if f in max_devs)
            evidence = {
                "rest_length": f"{rest_len:.4f}",
                "max_deviation_ratio": f"{peak_dev:.4f}",
            }
            fid = generate_finding_id(
                AnomalyType.BONE_LENGTH_VIOLATION,
                child.name,
                f_start,
                f_end,
                evidence,
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=child.name,
                    affected_body_part=categorize_body_part(child.name),
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(s * dt, 6),
                    time_end=round(e * dt, 6),
                    anomaly_type=AnomalyType.BONE_LENGTH_VIOLATION,
                    severity=Severity.CRITICAL if peak_dev > 0.08 else Severity.HIGH,
                    confidence=0.98,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Bone length violation on segment {parent.name}->{child.name}: length deviated by {peak_dev * 100:.1f}%.",
                )
            )

    for joint in parsed.ordered_joints:
        if not joint.parent_name or joint.parent_name not in parsed.joint_map:
            continue
        parent = parsed.joint_map[joint.parent_name]
        has_trans = any("position" in ch.lower() for ch in joint.channels)
        if has_trans:
            c_pos = joint_positions.get(joint.name, [])
            p_pos = joint_positions.get(parent.name, [])
            rest_len = vec_norm(joint.offset)
            disloc_frames: List[int] = []
            for t in range(len(c_pos)):
                curr_len = vec_dist(c_pos[t], p_pos[t])
                if abs(curr_len - rest_len) > scale * 0.04:
                    disloc_frames.append(t)
            intervals = merge_frame_intervals(disloc_frames, max_gap=2)
            for s, e in intervals:
                f_start = s + 1
                f_end = e + 1
                evidence = {
                    "dislocation_distance": f"{scale * 0.05:.4f}",
                }
                fid = generate_finding_id(
                    AnomalyType.JOINT_DISLOCATION,
                    joint.name,
                    f_start,
                    f_end,
                    evidence,
                )
                findings.append(
                    Finding(
                        finding_id=fid,
                        affected_joint=joint.name,
                        affected_body_part=categorize_body_part(joint.name),
                        frame_start=f_start,
                        frame_end=f_end,
                        time_start=round(s * dt, 6),
                        time_end=round(e * dt, 6),
                        anomaly_type=AnomalyType.JOINT_DISLOCATION,
                        severity=Severity.CRITICAL,
                        confidence=0.95,
                        evidence=evidence,
                        detector_version=DETECTOR_VERSION,
                        explanation=f"Joint dislocation detected at {joint.name}.",
                    )
                )

    for joint in parsed.ordered_joints:
        lower = joint.name.lower()
        if "knee" in lower or "elbow" in lower:
            for ch_name, ch_idx in zip(joint.channels, joint.channel_indices):
                if "rotation" in ch_name.lower():
                    angles = [parsed.motion[t][ch_idx] for t in range(metadata.frame_count)]
                    hyp_frames: List[int] = []
                    for t, ang in enumerate(angles):
                        norm_ang = (ang + 180.0) % 360.0 - 180.0
                        if norm_ang < -4.0 or norm_ang > 165.0:
                            hyp_frames.append(t)
                    intervals = merge_frame_intervals(hyp_frames, max_gap=2)
                    for s, e in intervals:
                        if (e - s + 1) >= 2:
                            f_start = s + 1
                            f_end = e + 1
                            min_ang = min((angles[t] + 180.0) % 360.0 - 180.0 for t in range(s, e + 1))
                            evidence = {
                                "joint": joint.name,
                                "channel": ch_name,
                                "min_angle": f"{min_ang:.2f}",
                            }
                            fid = generate_finding_id(
                                AnomalyType.ROM_HYPEREXTENSION,
                                joint.name,
                                f_start,
                                f_end,
                                evidence,
                            )
                            findings.append(
                                Finding(
                                    finding_id=fid,
                                    affected_joint=joint.name,
                                    affected_body_part=categorize_body_part(joint.name),
                                    frame_start=f_start,
                                    frame_end=f_end,
                                    time_start=round(s * dt, 6),
                                    time_end=round(e * dt, 6),
                                    anomaly_type=AnomalyType.ROM_HYPEREXTENSION,
                                    severity=Severity.HIGH,
                                    confidence=0.93,
                                    evidence=evidence,
                                    detector_version=DETECTOR_VERSION,
                                    explanation=f"Range of motion hyperextension on {joint.name} {ch_name} (angle {min_ang:.1f} deg).",
                                )
                            )

    return findings


def detect_contact_and_ground(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    joint_positions: Dict[str, List[List[float]]],
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> Tuple[List[Finding], bool]:
    findings, evaluated = detect_foot_sliding(parsed, metadata, joint_positions, whole_clip_stats=whole_clip_stats)
    if not evaluated:
        return findings, False

    dt = metadata.frame_time
    scale = metadata.skeleton_scale
    if scale <= 0.0 or not math.isfinite(scale) or metadata.frame_count < 4:
        return findings, True

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_joints: List[str] = []
    for j in parsed.ordered_joints:
        norm = j.name.lower().replace(" ", "").replace("_", "")
        if norm in candidate_foot_names:
            foot_joints.append(j.name)

    if not foot_joints:
        return findings, True

    if whole_clip_stats is not None:
        floor_y = whole_clip_stats.floor_y_p20
    else:
        all_y: List[float] = []
        for fj in foot_joints:
            all_y.extend(p[1] for p in joint_positions.get(fj, []))

        if not all_y:
            return findings, True

        sorted_y = sorted(all_y)
        floor_y = sorted_y[max(0, int(len(sorted_y) * 0.20))]
    penetration_thresh = floor_y - scale * 0.035

    for fj in foot_joints:
        positions = joint_positions.get(fj, [])
        pen_frames: List[int] = []
        for t, p in enumerate(positions):
            if p[1] < penetration_thresh:
                pen_frames.append(t)
        intervals = merge_frame_intervals(pen_frames, max_gap=2)
        for s, e in intervals:
            if (e - s + 1) >= 2:
                f_start = s + 1
                f_end = e + 1
                min_depth = min(positions[t][1] - floor_y for t in range(s, e + 1))
                evidence = {
                    "floor_y": f"{floor_y:.4f}",
                    "penetration_depth": f"{abs(min_depth):.4f}",
                }
                fid = generate_finding_id(
                    AnomalyType.GROUND_PENETRATION,
                    fj,
                    f_start,
                    f_end,
                    evidence,
                )
                findings.append(
                    Finding(
                        finding_id=fid,
                        affected_joint=fj,
                        affected_body_part=BodyPart.FOOT,
                        frame_start=f_start,
                        frame_end=f_end,
                        time_start=round(s * dt, 6),
                        time_end=round(e * dt, 6),
                        anomaly_type=AnomalyType.GROUND_PENETRATION,
                        severity=Severity.HIGH,
                        confidence=0.92,
                        evidence=evidence,
                        detector_version=DETECTOR_VERSION,
                        explanation=f"Ground penetration detected on {fj}: sank {abs(min_depth):.2f} units below floor level.",
                    )
                )

    hover_frames: List[int] = []
    hover_thresh = floor_y + scale * 0.08
    for t in range(metadata.frame_count):
        both_above = all(
            joint_positions[fj][t][1] > hover_thresh
            for fj in foot_joints
            if t < len(joint_positions.get(fj, []))
        )
        if both_above:
            hover_frames.append(t)

    intervals = merge_frame_intervals(hover_frames, max_gap=2)
    for s, e in intervals:
        span_len = e - s + 1
        if span_len >= 8 and (span_len * dt) >= 0.20:
            f_start = s + 1
            f_end = e + 1
            evidence = {
                "floor_y": f"{floor_y:.4f}",
                "duration_frames": span_len,
            }
            fid = generate_finding_id(
                AnomalyType.GROUND_HOVERING,
                foot_joints[0],
                f_start,
                f_end,
                evidence,
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=foot_joints[0],
                    affected_body_part=BodyPart.FOOT,
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(s * dt, 6),
                    time_end=round(e * dt, 6),
                    anomaly_type=AnomalyType.GROUND_HOVERING,
                    severity=Severity.MEDIUM,
                    confidence=0.88,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Ground hovering detected: character suspended in mid-air with no floor contact for {span_len} frames.",
                )
            )

    return findings, True


def detect_volumetric_self_collisions(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    joint_positions: Dict[str, List[List[float]]],
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    scale = metadata.skeleton_scale
    if scale <= 0.0 or not math.isfinite(scale) or metadata.frame_count < 2:
        return findings

    segments: List[Tuple[str, str, str]] = []
    for child in parsed.ordered_joints:
        if not child.parent_name or child.parent_name not in parsed.joint_map:
            continue
        parent = parsed.joint_map[child.parent_name]
        if vec_norm(child.offset) > scale * 0.05:
            segments.append((f"{parent.name}->{child.name}", parent.name, child.name))

    non_adjacent_pairs: List[Tuple[str, str, str, str, str, str]] = []
    ignored_keywords = ("shoulder", "spine", "neck", "head", "hip")
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            seg1, p1, c1 = segments[i]
            seg2, p2, c2 = segments[j]
            l1 = seg1.lower()
            l2 = seg2.lower()
            if any(k in l1 for k in ignored_keywords) or any(k in l2 for k in ignored_keywords):
                continue
            if p1 == p2 or p1 == c2 or c1 == p2 or c1 == c2:
                continue

            is_cross_leg = (("left" in l1 and "right" in l2) or ("right" in l1 and "left" in l2)) and ("leg" in l1 and "leg" in l2)
            is_cross_arm = (("left" in l1 and "right" in l2) or ("right" in l1 and "left" in l2)) and (("arm" in l1 or "hand" in l1) and ("arm" in l2 or "hand" in l2))
            is_hand_leg = (("hand" in l1 or "wrist" in l1) and "leg" in l2) or (("hand" in l2 or "wrist" in l2) and "leg" in l1)

            if not (is_cross_leg or is_cross_arm or is_hand_leg):
                continue

            node1_p = parsed.joint_map.get(p1).parent_name if p1 in parsed.joint_map else None
            node2_p = parsed.joint_map.get(p2).parent_name if p2 in parsed.joint_map else None
            if node1_p and node2_p and node1_p == node2_p and not is_cross_leg:
                continue

            non_adjacent_pairs.append((seg1, p1, c1, seg2, p2, c2))

    collision_thresh = scale * 0.012

    for seg1_name, p1_name, c1_name, seg2_name, p2_name, c2_name in non_adjacent_pairs:
        p1_pos = joint_positions.get(p1_name, [])
        c1_pos = joint_positions.get(c1_name, [])
        p2_pos = joint_positions.get(p2_name, [])
        c2_pos = joint_positions.get(c2_name, [])
        if not (p1_pos and c1_pos and p2_pos and c2_pos):
            continue

        coll_frames: List[int] = []
        min_dist_record: Dict[int, float] = {}
        for t in range(len(p1_pos)):
            d = segment_segment_distance(p1_pos[t], c1_pos[t], p2_pos[t], c2_pos[t])
            if d < collision_thresh:
                coll_frames.append(t)
                min_dist_record[t] = d

        intervals = merge_frame_intervals(coll_frames, max_gap=2)
        for s, e in intervals:
            span_len = e - s + 1
            if span_len >= 2:
                f_start = s + 1
                f_end = e + 1
                min_d = min(min_dist_record[t] for t in range(s, e + 1) if t in min_dist_record)
                evidence = {
                    "segment_a": seg1_name,
                    "segment_b": seg2_name,
                    "min_distance": f"{min_d:.4f}",
                    "threshold": f"{collision_thresh:.4f}",
                }
                fid = generate_finding_id(
                    AnomalyType.LIMB_SELF_COLLISION,
                    p1_name,
                    f_start,
                    f_end,
                    evidence,
                )
                findings.append(
                    Finding(
                        finding_id=fid,
                        affected_joint=p1_name,
                        affected_body_part=categorize_body_part(p1_name),
                        frame_start=f_start,
                        frame_end=f_end,
                        time_start=round(s * dt, 6),
                        time_end=round(e * dt, 6),
                        anomaly_type=AnomalyType.LIMB_SELF_COLLISION,
                        severity=Severity.HIGH,
                        confidence=0.90,
                        evidence=evidence,
                        detector_version=DETECTOR_VERSION,
                        explanation=f"Volumetric self-collision detected between limb segments {seg1_name} and {seg2_name} (clearance {min_d:.2f}).",
                    )
                )

    return findings


def detect_physical_dynamics(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    joint_positions: Dict[str, List[List[float]]],
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    scale = metadata.skeleton_scale
    if scale <= 0.0 or not math.isfinite(scale) or metadata.frame_count < 10:
        return findings

    com_traj: List[List[float]] = []
    for t in range(metadata.frame_count):
        pts = [
            joint_positions[j.name][t]
            for j in parsed.ordered_joints
            if t < len(joint_positions.get(j.name, []))
        ]
        if not pts:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        com_traj.append([cx, cy, cz])

    if len(com_traj) < 10:
        return findings

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_joints: List[str] = [
        j.name for j in parsed.ordered_joints
        if j.name.lower().replace(" ", "").replace("_", "") in candidate_foot_names
    ]
    if not foot_joints:
        return findings

    if whole_clip_stats is not None:
        floor_y = whole_clip_stats.floor_y_p05
    else:
        all_y: List[float] = []
        for fj in foot_joints:
            all_y.extend(p[1] for p in joint_positions.get(fj, []))
        floor_y = sorted(all_y)[max(0, int(len(all_y) * 0.05))] if all_y else 0.0
    contact_height = floor_y + scale * 0.08

    stride_k = max(1, round(0.08 / dt))
    dtk = stride_k * dt
    dtk2 = dtk * dtk
    g_eff = 9.81 * (scale / 1.75)

    zmp_frames: List[int] = []
    gravity_frames: List[int] = []
    grav_records: Dict[int, float] = {}

    for t in range(stride_k, len(com_traj) - stride_k):
        ax = (com_traj[t + stride_k][0] - 2.0 * com_traj[t][0] + com_traj[t - stride_k][0]) / dtk2
        ay = (com_traj[t + stride_k][1] - 2.0 * com_traj[t][1] + com_traj[t - stride_k][1]) / dtk2
        az = (com_traj[t + stride_k][2] - 2.0 * com_traj[t][2] + com_traj[t - stride_k][2]) / dtk2

        contact_feet = [
            fj for fj in foot_joints
            if t < len(joint_positions[fj]) and joint_positions[fj][t][1] <= contact_height
        ]

        if contact_feet:
            denom = ay + g_eff
            if abs(denom) > 1e-4 and (abs(ax) > 0.5 or abs(az) > 0.5):
                zmp_x = com_traj[t][0] - (com_traj[t][1] / denom) * ax
                zmp_z = com_traj[t][2] - (com_traj[t][1] / denom) * az

                min_fx = min(joint_positions[fj][t][0] for fj in contact_feet) - scale * 0.40
                max_fx = max(joint_positions[fj][t][0] for fj in contact_feet) + scale * 0.40
                min_fz = min(joint_positions[fj][t][2] for fj in contact_feet) - scale * 0.40
                max_fz = max(joint_positions[fj][t][2] for fj in contact_feet) + scale * 0.40

                if zmp_x < min_fx or zmp_x > max_fx or zmp_z < min_fz or zmp_z > max_fz:
                    zmp_frames.append(t)
        else:
            all_feet_high = all(
                t < len(joint_positions[fj]) and joint_positions[fj][t][1] > floor_y + scale * 0.10
                for fj in foot_joints
            )
            if all_feet_high:
                if ay > 10.0 or (abs(ay) < 0.2 and com_traj[t][1] > floor_y + scale * 0.30):
                    gravity_frames.append(t)
                    grav_records[t] = ay

    min_duration_frames = max(3, round(0.25 / dt))
    zmp_intervals = merge_frame_intervals(zmp_frames, max_gap=2)
    for s, e in zmp_intervals:
        span_len = e - s + 1
        if span_len >= min_duration_frames:
            f_start = s + 1
            f_end = e + 1
            evidence = {
                "support_phase": "stance",
                "duration_frames": span_len,
            }
            fid = generate_finding_id(
                AnomalyType.DYNAMIC_ZMP_VIOLATION,
                parsed.root_node.name,
                f_start,
                f_end,
                evidence,
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=parsed.root_node.name,
                    affected_body_part=BodyPart.PELVIS,
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(s * dt, 6),
                    time_end=round(e * dt, 6),
                    anomaly_type=AnomalyType.DYNAMIC_ZMP_VIOLATION,
                    severity=Severity.HIGH,
                    confidence=0.89,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Dynamic Zero Moment Point (ZMP) balance violation: ZMP outside foot support polygon for {span_len} frames.",
                )
            )

    grav_intervals = merge_frame_intervals(gravity_frames, max_gap=2)
    for s, e in grav_intervals:
        span_len = e - s + 1
        if span_len >= min_duration_frames:
            f_start = s + 1
            f_end = e + 1
            peak_ay = max(grav_records[t] for t in range(s, e + 1) if t in grav_records)
            evidence = {
                "observed_vert_accel": f"{peak_ay:.2f}",
                "expected_gravity": f"{-g_eff:.2f}",
            }
            fid = generate_finding_id(
                AnomalyType.BALLISTIC_GRAVITY_VIOLATION,
                parsed.root_node.name,
                f_start,
                f_end,
                evidence,
            )
            findings.append(
                Finding(
                    finding_id=fid,
                    affected_joint=parsed.root_node.name,
                    affected_body_part=BodyPart.PELVIS,
                    frame_start=f_start,
                    frame_end=f_end,
                    time_start=round(s * dt, 6),
                    time_end=round(e * dt, 6),
                    anomaly_type=AnomalyType.BALLISTIC_GRAVITY_VIOLATION,
                    severity=Severity.HIGH,
                    confidence=0.91,
                    evidence=evidence,
                    detector_version=DETECTOR_VERSION,
                    explanation=f"Ballistic gravity violation: vertical acceleration of {peak_ay:.1f} m/s^2 while airborne deviates from gravitational acceleration.",
                )
            )

    return findings


def get_joint_descendants(parsed: ParsedBVH) -> Dict[str, List[str]]:
    descendants: Dict[str, List[str]] = {j.name: [] for j in parsed.ordered_joints}
    for j in parsed.ordered_joints:
        stack = list(j.children)
        while stack:
            c = stack.pop()
            if c.name in descendants:
                descendants[j.name].append(c.name)
            stack.extend(c.children)
    return descendants


def assess_motion_pop_candidate(
    peak_departure: float,
    descendant_displacement: float,
    has_descendants: bool,
    anchor_unstable: bool,
    context_insufficient: bool,
    scale: float,
    is_boundary: bool,
) -> Tuple[AssessmentVerdict, Severity, float]:
    if context_insufficient or is_boundary:
        return AssessmentVerdict.INCONCLUSIVE, Severity.LOW, 0.40
    if anchor_unstable and peak_departure < 25.0:
        return AssessmentVerdict.INCONCLUSIVE, Severity.LOW, 0.45

    disp_thresh_visible = max(2.5, scale * 0.02) if scale > 0.0 else 2.5
    disp_thresh_review = max(0.8, scale * 0.006) if scale > 0.0 else 0.8

    if has_descendants:
        if peak_departure >= 15.0 and descendant_displacement >= disp_thresh_visible:
            sev = Severity.CRITICAL if (peak_departure >= 30.0 or descendant_displacement >= disp_thresh_visible * 2.0) else Severity.HIGH
            conf = 0.95 if not anchor_unstable else 0.85
            return AssessmentVerdict.LIKELY_VISIBLE_DEFECT, sev, conf
        if (peak_departure >= 10.0 and descendant_displacement >= disp_thresh_review) or (peak_departure >= 20.0 and descendant_displacement >= 1.0):
            conf = 0.75 if not anchor_unstable else 0.65
            return AssessmentVerdict.REVIEW, Severity.MEDIUM, conf
    else:
        if peak_departure >= 35.0 and descendant_displacement >= disp_thresh_visible:
            return AssessmentVerdict.LIKELY_VISIBLE_DEFECT, Severity.HIGH, 0.85
        if peak_departure >= 20.0 and descendant_displacement >= disp_thresh_review:
            return AssessmentVerdict.REVIEW, Severity.MEDIUM, 0.70

    return AssessmentVerdict.NUMERICAL_ONLY, Severity.LOW, 0.50


def detect_motion_pops(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
    include_all_verdicts: bool = False,
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    dt = metadata.frame_time
    fc = metadata.frame_count
    scale = metadata.skeleton_scale
    if fc < 8 or dt <= 0.0:
        return findings

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    desc_map = get_joint_descendants(parsed)
    windows_sec = (0.05, 0.10, 0.25)
    window_sizes = [max(2, round(w / dt)) for w in windows_sec]
    joint_parent_map = {j.name: j.parent_name for j in parsed.ordered_joints if j.parent_name}

    boundary_margin = max(3, round(0.06 / dt))
    raw_candidates = []

    for joint in parsed.ordered_joints:
        jname = joint.name
        rots = rep.local_rotations.get(jname, [])
        if len(rots) < fc:
            continue

        steps = [so3_geodesic_distance(rots[t - 1], rots[t]) for t in range(1, fc)]
        if not steps:
            continue

        step_accels = [abs(steps[t] - steps[t - 1]) / dt for t in range(1, len(steps))]
        if whole_clip_stats is not None and jname in whole_clip_stats.pop_thresholds:
            thresh_s, thresh_a = whole_clip_stats.pop_thresholds[jname]
        else:
            med_s = calc_median(steps)
            mad_s = calc_mad(steps, med_s)
            thresh_s = max(8.0, med_s + 5.0 * max(mad_s, 0.5))

            med_a = calc_median(step_accels)
            mad_a = calc_mad(step_accels, med_a)
            thresh_a = max(12000.0, 5.0 * max(mad_a, 500.0))

        flagged_frames = [idx + 1 for idx, s in enumerate(steps) if s > thresh_s or (0 < idx < len(steps) and step_accels[idx - 1] > thresh_a)]
        spike_frames = [t for t in range(1, fc - 1) if steps[t - 1] > thresh_s and (t < len(steps) and steps[t] > thresh_s) and so3_geodesic_distance(rots[t - 1], rots[t + 1]) < max(5.0, thresh_s * 0.5)]

        all_candidate_frames = sorted(set(flagged_frames + spike_frames))
        if not all_candidate_frames:
            continue

        merged_intervals = merge_frame_intervals(all_candidate_frames, max_gap=1)

        for s_idx, e_idx in merged_intervals:
            burst_len = e_idx - s_idx + 1
            if burst_len > round(0.40 / dt):
                continue

            extended_e = e_idx
            if extended_e < fc - 1 and steps[extended_e - 1] > thresh_s * 0.4:
                extended_e = min(fc - 1, extended_e + 1)

            ts = s_idx
            te = extended_e

            is_boundary = (ts <= boundary_margin) or (te >= fc - 1 - boundary_margin)
            has_left_anchor = ts >= 2
            has_right_anchor = te <= fc - 3
            context_insufficient = (not has_left_anchor and not has_right_anchor) or (is_boundary and fc < 15)

            anchor_unstable = False
            max_anchor_sigma = 0.0

            for kw in window_sizes:
                l_start = max(0, ts - kw)
                l_end = ts - 1
                r_start = te + 1
                r_end = min(fc - 1, te + kw)

                if has_left_anchor and l_end > l_start:
                    l_speeds = [steps[i - 1] / dt for i in range(l_start + 1, l_end + 1) if i - 1 < len(steps)]
                    if l_speeds:
                        mad_l = calc_mad(l_speeds, calc_median(l_speeds))
                        max_anchor_sigma = max(max_anchor_sigma, mad_l)
                        if mad_l > 1200.0:
                            anchor_unstable = True

                if has_right_anchor and r_end > r_start:
                    r_speeds = [steps[i - 1] / dt for i in range(r_start + 1, r_end + 1) if i - 1 < len(steps)]
                    if r_speeds:
                        mad_r = calc_mad(r_speeds, calc_median(r_speeds))
                        max_anchor_sigma = max(max_anchor_sigma, mad_r)
                        if mad_r > 1200.0:
                            anchor_unstable = True

            uncertainty = min(1.0, max_anchor_sigma / 1000.0) if not context_insufficient else 1.0

            is_spike = (ts == te)
            is_step = False
            if not is_spike and has_left_anchor and has_right_anchor:
                jump = so3_geodesic_distance(rots[ts - 1], rots[te + 1])
                pre_s = [steps[i - 1] for i in range(max(1, ts - 4), ts) if i - 1 < len(steps)]
                post_s = [steps[i - 1] for i in range(te + 1, min(fc, te + 5)) if i - 1 < len(steps)]
                if jump >= 15.0 and (calc_median(pre_s) < thresh_s * 0.5 if pre_s else False) and (calc_median(post_s) < thresh_s * 0.5 if post_s else False) and burst_len <= 2:
                    is_step = True

            pop_type = "boundary_event" if is_boundary else ("single_frame_spike" if is_spike else ("persistent_trajectory_step" if is_step else "multi_frame_burst"))

            departures = {}
            for t in range(ts, te + 1):
                if has_left_anchor and has_right_anchor:
                    u = (t - (ts - 1)) / ((te + 1) - (ts - 1))
                    r_pred = slerp_rotations(rots[ts - 1], rots[te + 1], u)
                elif has_left_anchor:
                    r_pred = rots[ts - 1]
                elif has_right_anchor:
                    r_pred = rots[te + 1]
                else:
                    r_pred = rots[t]
                departures[t] = so3_geodesic_distance(rots[t], r_pred)

            peak_t = max(departures.keys(), key=lambda k: departures[k])
            peak_dep = departures[peak_t]

            descendants = desc_map.get(jname, [])
            has_descendants = len(descendants) > 0
            max_desc_disp = 0.0
            worst_descendant = None

            eval_descendants = descendants if has_descendants else [jname]
            for d in eval_descendants:
                d_pos = rep.world_positions.get(d, [])
                if len(d_pos) < fc:
                    continue
                p_l = d_pos[ts - 1] if has_left_anchor else d_pos[0]
                p_r = d_pos[te + 1] if has_right_anchor else d_pos[-1]
                for t in range(ts, te + 1):
                    u = (t - (ts - 1)) / ((te + 1) - (ts - 1)) if has_left_anchor and has_right_anchor else 0.0
                    p_pred = [p_l[i] + u * (p_r[i] - p_l[i]) for i in range(3)] if has_left_anchor and has_right_anchor else (p_l if has_left_anchor else p_r)
                    disp = vec_dist(d_pos[t], p_pred)
                    if disp > max_desc_disp:
                        max_desc_disp = disp
                        worst_descendant = d

            verdict, severity, confidence = assess_motion_pop_candidate(
                peak_dep, max_desc_disp, has_descendants, anchor_unstable, context_insufficient, scale, is_boundary
            )

            raw_candidates.append({
                "joint": jname,
                "ts": ts,
                "te": te,
                "peak_t": peak_t,
                "peak_dep": peak_dep,
                "max_desc_disp": max_desc_disp,
                "worst_descendant": worst_descendant,
                "descendants": descendants,
                "verdict": verdict,
                "severity": severity,
                "confidence": confidence,
                "pop_type": pop_type,
                "anchor_unstable": anchor_unstable,
                "uncertainty": uncertainty,
                "threshold_deg": thresh_s,
            })

    originating = []
    for cand in raw_candidates:
        jname = cand["joint"]
        is_orig = True
        cand_peak = cand["peak_dep"]

        p_name = joint_parent_map.get(jname)
        while p_name:
            matching_parents = [
                c for c in raw_candidates
                if c["joint"] == p_name and (c["ts"] <= cand["te"] and c["te"] >= cand["ts"])
            ]
            for mp in matching_parents:
                if mp["peak_dep"] >= cand_peak * 0.9:
                    is_orig = False
                    break
            if not is_orig:
                break
            p_name = joint_parent_map.get(p_name)

        if is_orig:
            matching_children = [
                c for c in raw_candidates
                if c["joint"] in cand["descendants"] and (c["ts"] <= cand["te"] and c["te"] >= cand["ts"])
            ]
            if any(mc["peak_dep"] > cand_peak * 1.2 for mc in matching_children):
                is_orig = False

        if is_orig:
            originating.append(cand)

    for cand in originating:
        if not include_all_verdicts and cand["verdict"] in (AssessmentVerdict.NUMERICAL_ONLY, AssessmentVerdict.INCONCLUSIVE):
            continue

        evidence = {
            "metric_name": "physical_orientation_departure",
            "measured_value": round(cand["peak_dep"], 4),
            "threshold": round(cand["threshold_deg"], 4),
            "unit": "degrees",
            "peak_frame": cand["peak_t"],
            "display_peak_frame": cand["peak_t"] + 1,
            "originating_joint": cand["joint"],
            "pop_type": cand["pop_type"],
            "max_descendant_displacement": round(cand["max_desc_disp"], 4),
            "worst_descendant": cand["worst_descendant"],
            "descendant_joints": cand["descendants"][:5],
            "evaluated_windows_sec": list(windows_sec),
            "anchor_unstable": cand["anchor_unstable"],
            "uncertainty": round(cand["uncertainty"], 4),
        }

        fid = generate_finding_id(AnomalyType.ROTATION_JITTER, cand["joint"], cand["ts"], cand["te"], evidence)

        findings.append(Finding(
            finding_id=fid,
            affected_joint=cand["joint"],
            affected_body_part=categorize_body_part(cand["joint"]),
            frame_start=cand["ts"],
            frame_end=cand["te"],
            time_start=round(cand["ts"] * dt, 6),
            time_end=round(cand["te"] * dt, 6),
            anomaly_type=AnomalyType.ROTATION_JITTER,
            severity=cand["severity"],
            confidence=cand["confidence"],
            evidence=evidence,
            detector_version=DETECTOR_VERSION,
            explanation=f"Motion solve pop detected on {cand['joint']} ({cand['pop_type']}): peak departure {cand['peak_dep']:.1f} deg at frame {cand['peak_t']}.",
            verdict=cand["verdict"],
            peak_frame=cand["peak_t"],
            display_peak_frame=cand["peak_t"] + 1,
        ))

    return findings


class DefectCandidate(BaseModel):
    model_config = {"extra": "allow"}

    family: str
    anomaly_type: AnomalyType
    joint: str
    frame_start: int
    frame_end: int
    peak_frame: int
    metric_value: float
    metric_name: str
    threshold: float
    physical_displacement: float = 0.0
    verdict: AssessmentVerdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
    severity: Severity = Severity.MEDIUM
    confidence: float = 0.90
    has_context: bool = True
    missing_context_reason: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None:
                return val
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return self.__pydantic_extra__[key]
        if key in self.evidence:
            return self.evidence[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_finding(self, dt: float = 0.033333, detector_version: str = DETECTOR_VERSION) -> Finding:
        fid = generate_finding_id(self.anomaly_type, self.joint, self.frame_start, self.frame_end, self.evidence)
        return Finding(
            finding_id=fid,
            affected_joint=self.joint,
            affected_body_part=categorize_body_part(self.joint),
            frame_start=self.frame_start,
            frame_end=self.frame_end,
            time_start=round(self.frame_start * dt, 6),
            time_end=round(self.frame_end * dt, 6),
            anomaly_type=self.anomaly_type,
            severity=self.severity,
            confidence=self.confidence,
            evidence=self.evidence,
            detector_version=detector_version,
            explanation=self.explanation,
            verdict=self.verdict,
            peak_frame=self.peak_frame,
            display_peak_frame=self.peak_frame + 1,
        )


def generate_pop_jump_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if fc < 6 or dt <= 0.0:
        candidates.append(DefectCandidate(
            family="pops_jumps",
            anomaly_type=AnomalyType.ROTATION_JITTER,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="insufficient_frames",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="insufficient_frames",
            evidence={"frame_count": fc},
            explanation=f"Insufficient temporal context ({fc} frames) for pop/jump candidate evaluation.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    desc_map = get_joint_descendants(parsed)
    boundary_margin = max(2, round(0.05 / dt))

    for joint in parsed.ordered_joints:
        jname = joint.name
        rots = rep.local_rotations.get(jname, [])
        if len(rots) < fc:
            continue

        steps = [so3_geodesic_distance(rots[t - 1], rots[t]) for t in range(1, fc)]
        if not steps:
            continue

        med_s = calc_median(steps)
        mad_s = calc_mad(steps, med_s)
        thresh_s = max(8.0, med_s + 5.0 * max(mad_s, 0.5))

        step_accels = [abs(steps[t] - steps[t - 1]) / dt for t in range(1, len(steps))]
        med_a = calc_median(step_accels)
        mad_a = calc_mad(step_accels, med_a)
        thresh_a = max(12000.0, 5.0 * max(mad_a, 500.0))

        flagged_frames = [idx + 1 for idx, s in enumerate(steps) if s > thresh_s or (0 < idx < len(steps) and step_accels[idx - 1] > thresh_a)]
        spike_frames = [t for t in range(1, fc - 1) if steps[t - 1] > thresh_s and (t < len(steps) and steps[t] > thresh_s) and so3_geodesic_distance(rots[t - 1], rots[t + 1]) < max(5.0, thresh_s * 0.5)]

        all_candidate_frames = sorted(set(flagged_frames + spike_frames))
        if not all_candidate_frames:
            continue

        intervals = merge_frame_intervals(all_candidate_frames, max_gap=1)
        for ts, te in intervals:
            has_left_anchor = ts >= 2
            has_right_anchor = te <= fc - 3
            is_boundary = (ts <= boundary_margin) or (te >= fc - 1 - boundary_margin)
            has_context = has_left_anchor and has_right_anchor and not (is_boundary and fc < 12)

            departures: Dict[int, float] = {}
            for t in range(ts, te + 1):
                if has_left_anchor and has_right_anchor:
                    u = (t - (ts - 1)) / ((te + 1) - (ts - 1))
                    r_pred = slerp_rotations(rots[ts - 1], rots[te + 1], u)
                elif has_left_anchor:
                    r_pred = rots[ts - 1]
                elif has_right_anchor:
                    r_pred = rots[te + 1]
                else:
                    r_pred = rots[t]
                departures[t] = so3_geodesic_distance(rots[t], r_pred)

            peak_t = max(departures.keys(), key=lambda k: departures[k])
            peak_dep = departures[peak_t]

            descendants = desc_map.get(jname, [])
            eval_desc = descendants if descendants else [jname]
            max_disp = 0.0
            worst_desc = None
            for d in eval_desc:
                d_pos = rep.world_positions.get(d, [])
                if len(d_pos) < fc:
                    continue
                p_l = d_pos[ts - 1] if has_left_anchor else d_pos[0]
                p_r = d_pos[te + 1] if has_right_anchor else d_pos[-1]
                for t in range(ts, te + 1):
                    u = (t - (ts - 1)) / ((te + 1) - (ts - 1)) if has_left_anchor and has_right_anchor else 0.0
                    p_pred = [p_l[i] + u * (p_r[i] - p_l[i]) for i in range(3)] if has_left_anchor and has_right_anchor else (p_l if has_left_anchor else p_r)
                    disp = vec_dist(d_pos[t], p_pred)
                    if disp > max_disp:
                        max_disp = disp
                        worst_desc = d

            if not has_context:
                verdict = AssessmentVerdict.INCONCLUSIVE
                sev = Severity.LOW
                conf = 0.40
                reason = "boundary_context_missing" if is_boundary else "insufficient_anchors"
            else:
                verdict, sev, conf = assess_motion_pop_candidate(
                    peak_dep, max_disp, len(descendants) > 0, False, False, scale, False
                )
                reason = None

            ev = {
                "metric_name": "contextual_departure_angle",
                "measured_value": round(peak_dep, 4),
                "threshold": round(thresh_s, 4),
                "unit": "degrees",
                "peak_frame": peak_t,
                "display_peak_frame": peak_t + 1,
                "physical_displacement": round(max_disp, 4),
                "worst_descendant": worst_desc,
                "pop_type": "single_frame_spike" if ts == te else "multi_frame_burst",
                "has_context": has_context,
            }

            candidates.append(DefectCandidate(
                family="pops_jumps",
                anomaly_type=AnomalyType.ROTATION_JITTER,
                joint=jname,
                frame_start=ts,
                frame_end=te,
                peak_frame=peak_t,
                metric_value=round(peak_dep, 4),
                metric_name="contextual_departure_angle",
                threshold=round(thresh_s, 4),
                physical_displacement=round(max_disp, 4),
                verdict=verdict,
                severity=sev,
                confidence=conf,
                has_context=has_context,
                missing_context_reason=reason,
                evidence=ev,
                explanation=f"Pop candidate on {jname}: peak contextual departure {peak_dep:.1f} deg with {max_disp:.2f} physical displacement.",
            ))

    root = parsed.root_node
    root_pos = rep.world_positions.get(root.name, [])
    if len(root_pos) >= fc and fc >= 6:
        speeds = [vec_dist(root_pos[t], root_pos[t - 1]) / dt for t in range(1, fc)]
        med_v = calc_median(speeds)
        thresh_v = max(5.0 * med_v, max(2.0, scale * 2.0))
        flagged_root = [idx + 1 for idx, v in enumerate(speeds) if v > thresh_v]
        if flagged_root:
            intervals_root = merge_frame_intervals(flagged_root, max_gap=1)
            for ts, te in intervals_root:
                has_left = ts >= 2
                has_right = te <= fc - 3
                has_context = has_left and has_right
                peak_spd = max(speeds[t - 1] for t in range(ts, te + 1) if t - 1 < len(speeds))
                peak_f = ts
                disp_val = 0.0
                if has_context:
                    p_l = root_pos[ts - 1]
                    p_r = root_pos[te + 1]
                    for t in range(ts, te + 1):
                        u = (t - (ts - 1)) / ((te + 1) - (ts - 1))
                        pred = [p_l[i] + u * (p_r[i] - p_l[i]) for i in range(3)]
                        d = vec_dist(root_pos[t], pred)
                        if d > disp_val:
                            disp_val = d
                            peak_f = t
                if not has_context:
                    verdict = AssessmentVerdict.INCONCLUSIVE
                    sev = Severity.LOW
                    conf = 0.40
                    reason = "boundary_root_context_missing"
                elif peak_spd > thresh_v * 1.8 and disp_val >= max(1.0, scale * 0.02):
                    verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                    sev = Severity.HIGH
                    conf = 0.95
                    reason = None
                else:
                    verdict = AssessmentVerdict.REVIEW
                    sev = Severity.MEDIUM
                    conf = 0.70
                    reason = None

                ev = {
                    "metric_name": "root_jump_speed",
                    "measured_value": round(peak_spd, 4),
                    "threshold": round(thresh_v, 4),
                    "unit": "units_per_sec",
                    "peak_frame": peak_f,
                    "display_peak_frame": peak_f + 1,
                    "physical_displacement": round(disp_val, 4),
                    "has_context": has_context,
                }
                candidates.append(DefectCandidate(
                    family="pops_jumps",
                    anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
                    joint=root.name,
                    frame_start=ts,
                    frame_end=te,
                    peak_frame=peak_f,
                    metric_value=round(peak_spd, 4),
                    metric_name="root_jump_speed",
                    threshold=round(thresh_v, 4),
                    physical_displacement=round(disp_val, 4),
                    verdict=verdict,
                    severity=sev,
                    confidence=conf,
                    has_context=has_context,
                    missing_context_reason=reason,
                    evidence=ev,
                    explanation=f"Root jump discontinuity candidate: peak speed {peak_spd:.2f} units/s.",
                ))

    return candidates


def generate_repeated_jitter_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if fc < 6 or dt <= 0.0:
        candidates.append(DefectCandidate(
            family="repeated_jitter",
            anomaly_type=AnomalyType.ROTATION_JITTER,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="insufficient_frames",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="insufficient_frames_for_jitter",
            evidence={"frame_count": fc},
            explanation=f"Insufficient frames ({fc}) to assess sustained oscillation for jitter.",
        ))
        return candidates

    if scale <= 0.0 or not math.isfinite(scale):
        candidates.append(DefectCandidate(
            family="repeated_jitter",
            anomaly_type=AnomalyType.ROTATION_JITTER,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="invalid_scale",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="invalid_skeleton_scale",
            evidence={"skeleton_scale": scale},
            explanation="Invalid skeleton scale: cannot compute physical jitter displacement.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    desc_map = get_joint_descendants(parsed)

    for joint in parsed.ordered_joints:
        jname = joint.name
        rot_channels = [
            (ch_name, ch_idx)
            for ch_name, ch_idx in zip(joint.channels, joint.channel_indices)
            if "rotation" in ch_name.lower()
        ]
        for ch_name, ch_idx in rot_channels:
            raw_vals = [parsed.motion[t][ch_idx] for t in range(fc)]
            unwrapped = unwrap_angles(raw_vals)
            vels = [(unwrapped[t] - unwrapped[t - 1]) / dt for t in range(1, fc)]
            accels = [(vels[t] - vels[t - 1]) / dt for t in range(1, len(vels))]
            if not accels:
                continue

            med_a = calc_median(accels)
            mad_a = calc_mad(accels, med_a)
            thresh_a = max(15000.0, 4.0 * max(mad_a, 500.0))

            sign_reversals = 0
            for t in range(1, len(accels)):
                if (accels[t] * accels[t - 1] < 0.0) and (abs(accels[t]) > 2000.0 or abs(accels[t - 1]) > 2000.0):
                    sign_reversals += 1
            sar = sign_reversals / max(1, len(accels) - 1)

            flagged_frames = [t + 2 for t, a in enumerate(accels) if abs(a) > thresh_a]
            if not flagged_frames:
                continue

            intervals = merge_frame_intervals(flagged_frames, max_gap=2)
            for s, e in intervals:
                window_accels = accels[max(0, s - 2):min(len(accels), e + 1)]
                window_reversals = 0
                for i in range(1, len(window_accels)):
                    if (window_accels[i] * window_accels[i - 1] < 0.0):
                        window_reversals += 1
                window_sar = window_reversals / max(1, len(window_accels) - 1)

                p2p = max(unwrapped[s:e + 1]) - min(unwrapped[s:e + 1])
                peak_acc = max(abs(accels[t - 2]) for t in range(s, e + 1) if 0 <= t - 2 < len(accels))
                peak_f = max(range(s, e + 1), key=lambda t: abs(accels[t - 2]) if 0 <= t - 2 < len(accels) else 0.0)

                descendants = desc_map.get(jname, [])
                eval_desc = descendants if descendants else [jname]
                max_phys_disp = 0.0
                for d in eval_desc:
                    d_pos = rep.world_positions.get(d, [])
                    if len(d_pos) >= fc:
                        window_pos = d_pos[s:e + 1]
                        if len(window_pos) >= 2:
                            for pi in window_pos:
                                for pj in window_pos:
                                    dist = vec_dist(pi, pj)
                                    if dist > max_phys_disp:
                                        max_phys_disp = dist

                sustained_oscillation = (window_reversals >= 2 and window_sar >= 0.38 and p2p >= 12.0)
                significant_displacement = max_phys_disp >= max(0.8, scale * 0.012)

                if sustained_oscillation and significant_displacement:
                    verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                    sev = Severity.HIGH if peak_acc > thresh_a * 2.0 else Severity.MEDIUM
                    conf = 0.92
                elif sustained_oscillation and not significant_displacement:
                    verdict = AssessmentVerdict.NUMERICAL_ONLY
                    sev = Severity.LOW
                    conf = 0.60
                elif not sustained_oscillation and peak_acc > thresh_a:
                    verdict = AssessmentVerdict.NUMERICAL_ONLY
                    sev = Severity.LOW
                    conf = 0.50
                else:
                    continue

                ev = {
                    "metric_name": "angular_acceleration_oscillation",
                    "measured_value": round(peak_acc, 4),
                    "threshold": round(thresh_a, 4),
                    "unit": "deg_per_sec2",
                    "channel": ch_name,
                    "peak_frame": peak_f,
                    "display_peak_frame": peak_f + 1,
                    "peak_to_peak_amplitude": round(p2p, 4),
                    "sign_alternation_ratio": round(window_sar, 4),
                    "directional_reversals": window_reversals,
                    "physical_displacement": round(max_phys_disp, 4),
                    "sustained_oscillation": sustained_oscillation,
                    "significant_displacement": significant_displacement,
                }
                candidates.append(DefectCandidate(
                    family="repeated_jitter",
                    anomaly_type=AnomalyType.ROTATION_JITTER,
                    joint=jname,
                    frame_start=s,
                    frame_end=e,
                    peak_frame=peak_f,
                    metric_value=round(peak_acc, 4),
                    metric_name="angular_acceleration_oscillation",
                    threshold=round(thresh_a, 4),
                    physical_displacement=round(max_phys_disp, 4),
                    verdict=verdict,
                    severity=sev,
                    confidence=conf,
                    evidence=ev,
                    explanation=f"Repeated rotational jitter candidate on {jname} {ch_name}: {peak_acc:.1f} deg/s^2, SAR {window_sar:.2f}, displacement {max_phys_disp:.2f}.",
                ))

    return candidates


def generate_freeze_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if fc < 6 or dt <= 0.0:
        candidates.append(DefectCandidate(
            family="freezes",
            anomaly_type=AnomalyType.OPTICAL_OCCLUSION_FLATLINE,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="insufficient_frames",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="insufficient_frames_for_freeze",
            evidence={"frame_count": fc},
            explanation=f"Insufficient temporal duration ({fc} frames) to verify freeze cessation and continuation.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    for joint in parsed.ordered_joints:
        jname = joint.name
        pos_list = rep.world_positions.get(jname, [])
        rot_list = rep.local_rotations.get(jname, [])
        if len(pos_list) < fc or len(rot_list) < fc:
            continue

        lin_speeds = [vec_dist(pos_list[t], pos_list[t - 1]) / dt for t in range(1, fc)]
        ang_speeds = [so3_geodesic_distance(rot_list[t - 1], rot_list[t]) / dt for t in range(1, fc)]

        flat_frames: List[int] = []
        for t in range(1, fc):
            if lin_speeds[t - 1] < 1e-4 and ang_speeds[t - 1] < 1e-3:
                flat_frames.append(t)

        if not flat_frames:
            continue

        intervals = merge_frame_intervals(flat_frames, max_gap=1)
        for s, e in intervals:
            span_len = e - s + 1
            if span_len < 3 or (span_len * dt) < 0.06:
                continue

            has_pre_context = s >= 2
            has_post_context = e <= fc - 3
            has_context = has_pre_context and has_post_context

            if not has_context:
                candidates.append(DefectCandidate(
                    family="freezes",
                    anomaly_type=AnomalyType.OPTICAL_OCCLUSION_FLATLINE,
                    joint=jname,
                    frame_start=s,
                    frame_end=e,
                    peak_frame=s,
                    metric_value=round(span_len * dt, 4),
                    metric_name="frozen_duration_sec",
                    threshold=0.06,
                    physical_displacement=0.0,
                    verdict=AssessmentVerdict.INCONCLUSIVE,
                    severity=Severity.LOW,
                    confidence=0.45,
                    has_context=False,
                    missing_context_reason="boundary_context_missing_for_freeze",
                    evidence={
                        "frames_frozen": span_len,
                        "duration_seconds": round(span_len * dt, 4),
                        "has_pre_context": has_pre_context,
                        "has_post_context": has_post_context,
                    },
                    explanation=f"Freeze event on {jname} lacks boundary context (frames {s}-{e}).",
                ))
                continue

            pre_speeds = lin_speeds[max(0, s - 5):s - 1]
            pre_ang_speeds = ang_speeds[max(0, s - 5):s - 1]
            max_v_pre = max(pre_speeds) if pre_speeds else 0.0
            max_w_pre = max(pre_ang_speeds) if pre_ang_speeds else 0.0
            active_pre = (max_v_pre > max(0.4, scale * 0.015)) or (max_w_pre > 12.0)

            post_v = lin_speeds[e] if e < len(lin_speeds) else 0.0
            post_w = ang_speeds[e] if e < len(ang_speeds) else 0.0
            snap_disp = vec_dist(pos_list[min(fc - 1, e + 1)], pos_list[e])
            continuation_mismatch = (post_v > max(0.4, scale * 0.015)) or (post_w > 12.0) or (snap_disp > max(0.5, scale * 0.01))

            entry_speed_high = (bool(pre_ang_speeds) and pre_ang_speeds[-1] > 20.0) or (bool(pre_speeds) and pre_speeds[-1] > max(1.2, scale * 0.04))
            exit_speed_high = (post_w > 20.0) or (post_v > max(1.2, scale * 0.04)) or (snap_disp > max(1.0, scale * 0.02))
            intentional_hold = not (entry_speed_high and exit_speed_high)

            if active_pre and continuation_mismatch and not intentional_hold:
                verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                sev = Severity.HIGH
                conf = 0.94
            elif intentional_hold:
                verdict = AssessmentVerdict.NUMERICAL_ONLY
                sev = Severity.LOW
                conf = 0.70
            elif not active_pre:
                verdict = AssessmentVerdict.NUMERICAL_ONLY
                sev = Severity.LOW
                conf = 0.50
            else:
                verdict = AssessmentVerdict.REVIEW
                sev = Severity.MEDIUM
                conf = 0.75

            ev = {
                "metric_name": "frozen_duration_sec",
                "measured_value": round(span_len * dt, 4),
                "threshold": 0.06,
                "unit": "seconds",
                "peak_frame": s,
                "display_peak_frame": s + 1,
                "frames_frozen": span_len,
                "max_v_pre": round(max_v_pre, 4),
                "max_w_pre": round(max_w_pre, 4),
                "active_pre_motion": active_pre,
                "continuation_mismatch": continuation_mismatch,
                "snap_displacement": round(snap_disp, 4),
                "intentional_hold": intentional_hold,
            }
            candidates.append(DefectCandidate(
                family="freezes",
                anomaly_type=AnomalyType.OPTICAL_OCCLUSION_FLATLINE,
                joint=jname,
                frame_start=s,
                frame_end=e,
                peak_frame=s,
                metric_value=round(span_len * dt, 4),
                metric_name="frozen_duration_sec",
                threshold=0.06,
                physical_displacement=round(snap_disp, 4),
                verdict=verdict,
                severity=sev,
                confidence=conf,
                evidence=ev,
                explanation=f"Freeze candidate on {jname}: {span_len} frames flatline ({span_len * dt:.2f}s) with cessation mismatch.",
            ))

    return candidates


def generate_foot_sliding_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if scale <= 0.0 or not math.isfinite(scale) or fc < 4:
        candidates.append(DefectCandidate(
            family="foot_sliding",
            anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="invalid_scale_or_frames",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="invalid_scale_or_frames",
            evidence={"frame_count": fc, "skeleton_scale": scale},
            explanation="Invalid skeleton scale or frame count for foot sliding evaluation.",
        ))
        return candidates

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_joints = [
        j.name for j in parsed.ordered_joints
        if j.name.lower().replace(" ", "").replace("_", "") in candidate_foot_names
    ]

    if not foot_joints:
        candidates.append(DefectCandidate(
            family="foot_sliding",
            anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=fc - 1,
            peak_frame=0,
            metric_value=0.0,
            metric_name="missing_foot_joints",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="missing_foot_joints",
            evidence={},
            explanation="No foot or ankle joints identified in skeleton hierarchy.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    all_y: List[float] = []
    for fj in foot_joints:
        all_y.extend(p[1] for p in rep.world_positions.get(fj, []))

    if not all_y:
        return candidates

    sorted_y = sorted(all_y)
    floor_y = sorted_y[max(0, int(len(sorted_y) * 0.20))]
    contact_height_thresh = floor_y + scale * 0.02
    contact_vert_speed_thresh = scale * 0.08
    horizontal_drift_speed_threshold = scale * 0.35

    for foot_joint in foot_joints:
        positions = rep.world_positions.get(foot_joint, [])
        if len(positions) < 4:
            continue

        in_contact: List[int] = []
        for t in range(1, len(positions)):
            curr_y = positions[t][1]
            vy = abs(curr_y - positions[t - 1][1]) / dt
            if (curr_y <= contact_height_thresh) and (vy <= contact_vert_speed_thresh):
                in_contact.append(t)

        intervals = merge_frame_intervals(in_contact, max_gap=2)
        for cs, ce in intervals:
            duration = (ce - cs + 1) * dt
            if duration < 0.06:
                continue

            stance_drift = 0.0
            slide_speeds: List[float] = []
            slide_frames: List[int] = []
            for t in range(cs, ce + 1):
                dx = positions[t][0] - positions[t - 1][0]
                dz = positions[t][2] - positions[t - 1][2]
                disp = math.sqrt(dx * dx + dz * dz)
                stance_drift += disp
                h_spd = disp / dt
                slide_speeds.append(h_spd)
                if h_spd > horizontal_drift_speed_threshold:
                    slide_frames.append(t)

            max_drift_spd = max(slide_speeds) if slide_speeds else 0.0
            peak_f = max(range(cs, ce + 1), key=lambda t: slide_speeds[t - cs] if t - cs < len(slide_speeds) else 0.0)

            accum_thresh = scale * 0.08
            if max_drift_spd > horizontal_drift_speed_threshold and stance_drift >= accum_thresh:
                verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                sev = Severity.HIGH if max_drift_spd > horizontal_drift_speed_threshold * 1.8 else Severity.MEDIUM
                conf = 0.92
            elif max_drift_spd > horizontal_drift_speed_threshold * 0.6 and stance_drift >= scale * 0.04:
                verdict = AssessmentVerdict.REVIEW
                sev = Severity.MEDIUM
                conf = 0.70
            elif stance_drift > 0.0:
                verdict = AssessmentVerdict.NUMERICAL_ONLY
                sev = Severity.LOW
                conf = 0.50
            else:
                continue

            ev = {
                "metric_name": "accumulated_stance_drift",
                "measured_value": round(stance_drift, 4),
                "threshold": round(accum_thresh, 4),
                "unit": "units",
                "peak_frame": peak_f,
                "display_peak_frame": peak_f + 1,
                "max_drift_speed": round(max_drift_spd, 4),
                "speed_threshold": round(horizontal_drift_speed_threshold, 4),
                "duration_seconds": round(duration, 4),
                "floor_y": round(floor_y, 4),
            }
            candidates.append(DefectCandidate(
                family="foot_sliding",
                anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
                joint=foot_joint,
                frame_start=cs,
                frame_end=ce,
                peak_frame=peak_f,
                metric_value=round(stance_drift, 4),
                metric_name="accumulated_stance_drift",
                threshold=round(accum_thresh, 4),
                physical_displacement=round(stance_drift, 4),
                verdict=verdict,
                severity=sev,
                confidence=conf,
                evidence=ev,
                explanation=f"Planted foot sliding candidate on {foot_joint}: accumulated drift {stance_drift:.2f} units, peak speed {max_drift_spd:.2f} units/s.",
            ))

    return candidates


def generate_ground_contact_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if scale <= 0.0 or not math.isfinite(scale) or fc < 4:
        candidates.append(DefectCandidate(
            family="ground_contact",
            anomaly_type=AnomalyType.GROUND_HOVERING,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="invalid_scale_or_frames",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="invalid_scale_or_frames",
            evidence={"frame_count": fc},
            explanation="Invalid scale or frame count for ground contact evaluation.",
        ))
        return candidates

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_joints = [
        j.name for j in parsed.ordered_joints
        if j.name.lower().replace(" ", "").replace("_", "") in candidate_foot_names
    ]

    if not foot_joints:
        candidates.append(DefectCandidate(
            family="ground_contact",
            anomaly_type=AnomalyType.GROUND_HOVERING,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=fc - 1,
            peak_frame=0,
            metric_value=0.0,
            metric_name="missing_foot_joints",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="missing_foot_joints",
            evidence={},
            explanation="Missing foot joints: cannot establish ground contacts.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    all_y: List[float] = []
    for fj in foot_joints:
        all_y.extend(p[1] for p in rep.world_positions.get(fj, []))

    if not all_y:
        return candidates

    stable_contact_y: List[float] = []
    for t in range(1, fc):
        for fj in foot_joints:
            pos = rep.world_positions.get(fj, [])
            if t < len(pos):
                vy = abs(pos[t][1] - pos[t - 1][1]) / dt
                if vy <= scale * 0.08:
                    stable_contact_y.append(pos[t][1])

    if stable_contact_y:
        sorted_contact = sorted(stable_contact_y)
        floor_y = sorted_contact[max(0, int(len(sorted_contact) * 0.35))]
    else:
        sorted_y = sorted(all_y)
        floor_y = sorted_y[max(0, int(len(sorted_y) * 0.35))]

    min_foot_y_per_frame = [
        min(rep.world_positions[fj][t][1] for fj in foot_joints if t < len(rep.world_positions.get(fj, [])))
        for t in range(fc)
    ]
    min_elev = min(min_foot_y_per_frame)
    is_ungrounded = (min_elev > scale * 0.35 and len(stable_contact_y) < max(2, int(fc * 0.1))) or (min_elev > scale * 0.5)
    if is_ungrounded:
        candidates.append(DefectCandidate(
            family="ground_contact",
            anomaly_type=AnomalyType.GROUND_HOVERING,
            joint=foot_joints[0],
            frame_start=0,
            frame_end=fc - 1,
            peak_frame=0,
            metric_value=round(min(min_foot_y_per_frame) - floor_y, 4),
            metric_name="ungrounded_elevation",
            threshold=round(scale * 0.10, 4),
            physical_displacement=round(min(min_foot_y_per_frame) - floor_y, 4),
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.50,
            has_context=False,
            missing_context_reason="ungrounded_scene",
            evidence={"floor_y": round(floor_y, 4), "min_foot_y": round(min(min_foot_y_per_frame), 4)},
            explanation="Scene appears ungrounded: no stable floor contact baseline established.",
        ))
        return candidates

    pen_thresh = floor_y - scale * 0.035
    for fj in foot_joints:
        positions = rep.world_positions.get(fj, [])
        pen_frames = [t for t, p in enumerate(positions) if p[1] < pen_thresh]
        intervals = merge_frame_intervals(pen_frames, max_gap=2)
        for s, e in intervals:
            if (e - s + 1) >= 2:
                max_depth = max(floor_y - positions[t][1] for t in range(s, e + 1))
                peak_f = max(range(s, e + 1), key=lambda t: floor_y - positions[t][1])
                ev = {
                    "metric_name": "ground_penetration_depth",
                    "measured_value": round(max_depth, 4),
                    "threshold": round(scale * 0.035, 4),
                    "unit": "units",
                    "peak_frame": peak_f,
                    "display_peak_frame": peak_f + 1,
                    "floor_y": round(floor_y, 4),
                    "penetration_depth": round(max_depth, 4),
                }
                candidates.append(DefectCandidate(
                    family="ground_contact",
                    anomaly_type=AnomalyType.GROUND_PENETRATION,
                    joint=fj,
                    frame_start=s,
                    frame_end=e,
                    peak_frame=peak_f,
                    metric_value=round(max_depth, 4),
                    metric_name="ground_penetration_depth",
                    threshold=round(scale * 0.035, 4),
                    physical_displacement=round(max_depth, 4),
                    verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                    severity=Severity.HIGH,
                    confidence=0.92,
                    evidence=ev,
                    explanation=f"Ground penetration candidate on {fj}: sank {max_depth:.2f} units below floor.",
                ))

    hover_thresh = floor_y + scale * 0.08
    hover_frames = [t for t, y in enumerate(min_foot_y_per_frame) if y > hover_thresh]
    intervals_hover = merge_frame_intervals(hover_frames, max_gap=2)
    for s, e in intervals_hover:
        span_len = e - s + 1
        if span_len >= 8 and (span_len * dt) >= 0.20:
            has_takeoff = (s >= 2) and any(min_foot_y_per_frame[t] <= floor_y + scale * 0.03 for t in range(max(0, s - 4), s))
            has_landing = (e <= fc - 3) and any(min_foot_y_per_frame[t] <= floor_y + scale * 0.03 for t in range(e + 1, min(fc, e + 5)))

            root_pos = rep.world_positions.get(parsed.root_node.name, [])
            is_ballistic_jump = False
            if has_takeoff and has_landing and len(root_pos) >= fc:
                mid_f = int((s + e) / 2)
                peak_height = root_pos[mid_f][1]
                start_height = root_pos[s][1]
                end_height = root_pos[e][1]
                if peak_height > start_height and peak_height > end_height:
                    is_ballistic_jump = True

            if is_ballistic_jump:
                verdict = AssessmentVerdict.NUMERICAL_ONLY
                sev = Severity.LOW
                conf = 0.60
            else:
                verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                sev = Severity.MEDIUM
                conf = 0.88

            max_elev = max(min_foot_y_per_frame[t] - floor_y for t in range(s, e + 1))
            peak_f = max(range(s, e + 1), key=lambda t: min_foot_y_per_frame[t])
            ev = {
                "metric_name": "unsupported_hover_duration",
                "measured_value": round(span_len * dt, 4),
                "threshold": 0.20,
                "unit": "seconds",
                "peak_frame": peak_f,
                "display_peak_frame": peak_f + 1,
                "floor_y": round(floor_y, 4),
                "hover_elevation": round(max_elev, 4),
                "duration_frames": span_len,
                "is_ballistic_jump": is_ballistic_jump,
            }
            candidates.append(DefectCandidate(
                family="ground_contact",
                anomaly_type=AnomalyType.GROUND_HOVERING,
                joint=foot_joints[0],
                frame_start=s,
                frame_end=e,
                peak_frame=peak_f,
                metric_value=round(span_len * dt, 4),
                metric_name="unsupported_hover_duration",
                threshold=0.20,
                physical_displacement=round(max_elev, 4),
                verdict=verdict,
                severity=sev,
                confidence=conf,
                evidence=ev,
                explanation=f"Unsupported ground hovering candidate: character suspended {max_elev:.2f} units for {span_len} frames.",
            ))

    return candidates


def generate_biomechanical_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if scale <= 0.0 or not math.isfinite(scale) or fc < 2:
        candidates.append(DefectCandidate(
            family="biomechanical",
            anomaly_type=AnomalyType.ROM_HYPEREXTENSION,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="invalid_scale_or_frames",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="invalid_scale_or_frames",
            evidence={"frame_count": fc},
            explanation="Invalid scale or frame count for biomechanical ROM evaluation.",
        ))
        return candidates

    target_joints = [
        j for j in parsed.ordered_joints
        if any(k in j.name.lower() for k in ("knee", "elbow", "leg", "arm", "spine"))
    ]

    if not target_joints:
        candidates.append(DefectCandidate(
            family="biomechanical",
            anomaly_type=AnomalyType.ROM_HYPEREXTENSION,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=fc - 1,
            peak_frame=0,
            metric_value=0.0,
            metric_name="missing_biomechanical_joints",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="missing_biomechanical_joints",
            evidence={},
            explanation="Missing anatomical knee or elbow joints in hierarchy.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    for joint in target_joints:
        lower = joint.name.lower()
        is_knee = "knee" in lower or "leg" in lower
        is_elbow = "elbow" in lower or "arm" in lower

        for ch_name, ch_idx in zip(joint.channels, joint.channel_indices):
            if "rotation" not in ch_name.lower():
                continue
            angles = [parsed.motion[t][ch_idx] for t in range(fc)]
            norm_angles = [(a + 180.0) % 360.0 - 180.0 for a in angles]

            hyp_thresh = -4.0 if is_knee else (-5.0 if is_elbow else -15.0)
            flex_thresh = 165.0

            hyp_frames = [t for t, ang in enumerate(norm_angles) if (ang < hyp_thresh or ang > flex_thresh)]
            intervals = merge_frame_intervals(hyp_frames, max_gap=2)
            for s, e in intervals:
                if (e - s + 1) >= 2:
                    worst_ang = min(norm_angles[t] for t in range(s, e + 1))
                    peak_f = min(range(s, e + 1), key=lambda t: norm_angles[t])

                    if worst_ang < hyp_thresh - 5.0:
                        verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                        sev = Severity.HIGH
                        conf = 0.93
                    elif worst_ang < hyp_thresh:
                        verdict = AssessmentVerdict.REVIEW
                        sev = Severity.MEDIUM
                        conf = 0.75
                    elif worst_ang > 170.0:
                        verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
                        sev = Severity.HIGH
                        conf = 0.90
                    else:
                        verdict = AssessmentVerdict.NUMERICAL_ONLY
                        sev = Severity.LOW
                        conf = 0.50

                    ev = {
                        "metric_name": "anatomical_relative_angle",
                        "measured_value": round(worst_ang, 2),
                        "threshold": round(hyp_thresh, 2),
                        "unit": "degrees",
                        "joint": joint.name,
                        "channel": ch_name,
                        "peak_frame": peak_f,
                        "display_peak_frame": peak_f + 1,
                    }
                    candidates.append(DefectCandidate(
                        family="biomechanical",
                        anomaly_type=AnomalyType.ROM_HYPEREXTENSION,
                        joint=joint.name,
                        frame_start=s,
                        frame_end=e,
                        peak_frame=peak_f,
                        metric_value=round(worst_ang, 2),
                        metric_name="anatomical_relative_angle",
                        threshold=round(hyp_thresh, 2),
                        physical_displacement=round(abs(worst_ang - hyp_thresh), 2),
                        verdict=verdict,
                        severity=sev,
                        confidence=conf,
                        evidence=ev,
                        explanation=f"Biomechanical ROM violation on {joint.name} {ch_name}: relative angle {worst_ang:.1f} deg violates limit {hyp_thresh:.1f} deg.",
                    ))

    for child in parsed.ordered_joints:
        if not child.parent_name or child.parent_name not in parsed.joint_map:
            continue
        parent = parsed.joint_map[child.parent_name]
        rest_len = vec_norm(child.offset)
        if rest_len < scale * 0.02:
            continue

        c_pos = rep.world_positions.get(child.name, [])
        p_pos = rep.world_positions.get(parent.name, [])
        if len(c_pos) != len(p_pos) or not c_pos:
            continue

        devs: Dict[int, float] = {}
        for t in range(len(c_pos)):
            curr_len = vec_dist(c_pos[t], p_pos[t])
            dev = abs(curr_len - rest_len) / rest_len
            if dev > 0.025:
                devs[t] = dev

        intervals_bone = merge_frame_intervals(list(devs.keys()), max_gap=2)
        for s, e in intervals_bone:
            peak_dev = max(devs[t] for t in range(s, e + 1) if t in devs)
            peak_f = max(range(s, e + 1), key=lambda t: devs.get(t, 0.0))
            ev = {
                "metric_name": "bone_length_deviation_ratio",
                "measured_value": round(peak_dev, 4),
                "threshold": 0.025,
                "unit": "ratio",
                "rest_length": round(rest_len, 4),
                "peak_frame": peak_f,
                "display_peak_frame": peak_f + 1,
            }
            candidates.append(DefectCandidate(
                family="biomechanical",
                anomaly_type=AnomalyType.BONE_LENGTH_VIOLATION,
                joint=child.name,
                frame_start=s,
                frame_end=e,
                peak_frame=peak_f,
                metric_value=round(peak_dev, 4),
                metric_name="bone_length_deviation_ratio",
                threshold=0.025,
                physical_displacement=round(peak_dev * rest_len, 4),
                verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                severity=Severity.CRITICAL if peak_dev > 0.08 else Severity.HIGH,
                confidence=0.98,
                evidence=ev,
                explanation=f"Bone length violation on {parent.name}->{child.name}: length deviated by {peak_dev * 100:.1f}%.",
            ))

    return candidates


def generate_long_term_drift_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> List[DefectCandidate]:
    candidates: List[DefectCandidate] = []
    fc = metadata.frame_count
    dt = metadata.frame_time
    scale = metadata.skeleton_scale

    if fc < 12 or dt <= 0.0 or (fc * dt) < 0.35:
        candidates.append(DefectCandidate(
            family="long_term_drift",
            anomaly_type=AnomalyType.LONG_TERM_DRIFT,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=max(0, fc - 1),
            peak_frame=0,
            metric_value=0.0,
            metric_name="insufficient_duration",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="insufficient_duration_for_drift",
            evidence={"frame_count": fc, "duration_sec": round(fc * dt, 4)},
            explanation=f"Insufficient clip duration ({fc * dt:.2f}s) to observe long-term drift.",
        ))
        return candidates

    if scale <= 0.0 or not math.isfinite(scale):
        candidates.append(DefectCandidate(
            family="long_term_drift",
            anomaly_type=AnomalyType.LONG_TERM_DRIFT,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=fc - 1,
            peak_frame=0,
            metric_value=0.0,
            metric_name="invalid_scale",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="invalid_scale",
            evidence={"skeleton_scale": scale},
            explanation="Invalid scale for long-term drift evaluation.",
        ))
        return candidates

    candidate_foot_names = {"foot", "toe", "ankle", "leftfoot", "rightfoot", "left_foot", "right_foot"}
    foot_joints = [
        j.name for j in parsed.ordered_joints
        if j.name.lower().replace(" ", "").replace("_", "") in candidate_foot_names
    ]

    if not foot_joints:
        candidates.append(DefectCandidate(
            family="long_term_drift",
            anomaly_type=AnomalyType.LONG_TERM_DRIFT,
            joint=parsed.root_node.name,
            frame_start=0,
            frame_end=fc - 1,
            peak_frame=0,
            metric_value=0.0,
            metric_name="missing_foot_contacts",
            threshold=0.0,
            physical_displacement=0.0,
            verdict=AssessmentVerdict.INCONCLUSIVE,
            severity=Severity.LOW,
            confidence=0.40,
            has_context=False,
            missing_context_reason="no_contact_reference_for_drift",
            evidence={},
            explanation="No foot contacts to verify whether root movement is consistent with support.",
        ))
        return candidates

    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)

    all_y: List[float] = []
    for fj in foot_joints:
        all_y.extend(p[1] for p in rep.world_positions.get(fj, []))
    floor_y = sorted(all_y)[max(0, int(len(all_y) * 0.20))] if all_y else 0.0

    contact_h = floor_y + scale * 0.02
    contact_vy = scale * 0.08
    contact_vert_speed_thresh = scale * 0.08
    planted_frames: List[int] = []

    for t in range(1, fc):
        foot_contact_count = 0
        for fj in foot_joints:
            p = rep.world_positions[fj][t]
            p_prev = rep.world_positions[fj][t - 1]
            vy = abs(p[1] - p_prev[1]) / dt
            h_spd = math.sqrt((p[0] - p_prev[0]) ** 2 + (p[2] - p_prev[2]) ** 2) / dt
            if p[1] <= contact_h and vy <= contact_vert_speed_thresh and h_spd <= scale * 0.35:
                foot_contact_count += 1
        if foot_contact_count >= 1:
            planted_frames.append(t)

    intervals = merge_frame_intervals(planted_frames, max_gap=2)
    root = parsed.root_node
    root_pos = rep.world_positions.get(root.name, [])

    target_yaw_ch = "Zrotation" if rep.detected_up_axis == "Z" else "Yrotation"
    yaw_idx = None
    for ch_name, ch_idx in zip(root.channels, root.channel_indices):
        if ch_name == target_yaw_ch:
            yaw_idx = ch_idx
            break

    for s, e in intervals:
        span_len = e - s + 1
        if span_len < 10 or (span_len * dt) < 0.25:
            continue

        if yaw_idx is not None:
            raw_yaw = [parsed.motion[t][yaw_idx] for t in range(s, e + 1)]
            unwrapped_yaw = unwrap_angles(raw_yaw)
            yaw_drift = abs(unwrapped_yaw[-1] - unwrapped_yaw[0])
            yaw_step_speeds = [abs(unwrapped_yaw[i] - unwrapped_yaw[i - 1]) / dt for i in range(1, len(unwrapped_yaw))]
            max_yaw_spd = max(yaw_step_speeds) if yaw_step_speeds else 0.0

            if yaw_drift >= 10.0 and max_yaw_spd < 150.0:
                ev = {
                    "metric_name": "root_yaw_stance_drift",
                    "measured_value": round(yaw_drift, 4),
                    "threshold": 10.0,
                    "unit": "degrees",
                    "peak_frame": e,
                    "display_peak_frame": e + 1,
                    "duration_seconds": round(span_len * dt, 4),
                    "duration_frames": span_len,
                    "max_step_speed": round(max_yaw_spd, 4),
                }
                candidates.append(DefectCandidate(
                    family="long_term_drift",
                    anomaly_type=AnomalyType.LONG_TERM_DRIFT,
                    joint=root.name,
                    frame_start=s,
                    frame_end=e,
                    peak_frame=e,
                    metric_value=round(yaw_drift, 4),
                    metric_name="root_yaw_stance_drift",
                    threshold=10.0,
                    physical_displacement=round(yaw_drift, 4),
                    verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                    severity=Severity.HIGH,
                    confidence=0.92,
                    evidence=ev,
                    explanation=f"Long-term root yaw drift of {yaw_drift:.1f} deg during planted stance interval (frames {s}-{e}).",
                ))

        if len(root_pos) >= fc:
            dx = root_pos[e][0] - root_pos[s][0]
            dz = root_pos[e][2] - root_pos[s][2]
            trans_drift = math.sqrt(dx * dx + dz * dz)
            step_speeds = [vec_dist(root_pos[t], root_pos[t - 1]) / dt for t in range(s + 1, e + 1)]
            max_spd = max(step_speeds) if step_speeds else 0.0

            if trans_drift >= scale * 0.08 and max_spd < scale * 1.5:
                ev = {
                    "metric_name": "root_translation_stance_drift",
                    "measured_value": round(trans_drift, 4),
                    "threshold": round(scale * 0.08, 4),
                    "unit": "units",
                    "peak_frame": e,
                    "display_peak_frame": e + 1,
                    "duration_seconds": round(span_len * dt, 4),
                    "duration_frames": span_len,
                }
                candidates.append(DefectCandidate(
                    family="long_term_drift",
                    anomaly_type=AnomalyType.LONG_TERM_DRIFT,
                    joint=root.name,
                    frame_start=s,
                    frame_end=e,
                    peak_frame=e,
                    metric_value=round(trans_drift, 4),
                    metric_name="root_translation_stance_drift",
                    threshold=round(scale * 0.08, 4),
                    physical_displacement=round(trans_drift, 4),
                    verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
                    severity=Severity.HIGH,
                    confidence=0.90,
                    evidence=ev,
                    explanation=f"Long-term root translation drift of {trans_drift:.2f} units during planted stance interval (frames {s}-{e}).",
                ))

    return candidates


def generate_all_family_candidates(
    parsed: ParsedBVH,
    metadata: BVHMetadata,
    rep: Optional[SharedMotionRepresentation] = None,
) -> Dict[str, List[DefectCandidate]]:
    if rep is None:
        rep = SharedMotionRepresentation(parsed, normalize_coordinates=False)
    return {
        "pops_jumps": generate_pop_jump_candidates(parsed, metadata, rep=rep),
        "repeated_jitter": generate_repeated_jitter_candidates(parsed, metadata, rep=rep),
        "freezes": generate_freeze_candidates(parsed, metadata, rep=rep),
        "foot_sliding": generate_foot_sliding_candidates(parsed, metadata, rep=rep),
        "ground_contact": generate_ground_contact_candidates(parsed, metadata, rep=rep),
        "biomechanical": generate_biomechanical_candidates(parsed, metadata, rep=rep),
        "long_term_drift": generate_long_term_drift_candidates(parsed, metadata, rep=rep),
    }


class EventMatchResult(BaseModel):
    clip_name: str
    total_gt_events: int
    matched_gt_events: int
    confirmed_recall: float
    review_inclusive_recall: float
    defective_frame_coverage: float
    excess_good_frames_flagged: int
    joint_attribution_accuracy: float
    duplicate_penalties: int
    excess_width_penalties: int
    matched_pairs: List[Dict[str, Any]] = Field(default_factory=list)
    unmatched_gt: List[Dict[str, Any]] = Field(default_factory=list)
    unmatched_detections: List[Dict[str, Any]] = Field(default_factory=list)
    duplicate_detections: List[Dict[str, Any]] = Field(default_factory=list)


def evaluate_clip_events(
    clip_name: str,
    findings: List[Finding],
    manifest: Dict[str, Any],
    dt: float,
) -> EventMatchResult:
    gt_defective: List[Dict[str, Any]] = manifest.get("confirmed_defective", [])
    acceptable_map: Dict[str, List[List[int]]] = manifest.get("confirmed_acceptable", {})
    uncertain_map: Dict[str, List[List[int]]] = manifest.get("transition_uncertain", {})
    originating_joints: List[str] = manifest.get("originating_joints", [])

    t_peak = max(2, int(round(0.05 / dt)))

    candidate_matches: List[Tuple[float, float, int, Finding, Dict[str, Any]]] = []
    for d in findings:
        d_s, d_e = d.frame_start, d.frame_end
        d_peak = d.peak_frame if d.peak_frame is not None else int(round((d_s + d_e) / 2.0))
        for g_idx, g in enumerate(gt_defective):
            g_joint = g.get("joint")
            if d.affected_joint != g_joint:
                continue
            g_s, g_e = g.get("frames_0_based", [0, 0])
            g_peak = g.get("peak_frame", int(round((g_s + g_e) / 2.0)))

            inter = max(0, min(d_e, g_e) - max(d_s, g_s) + 1)
            union = (d_e - d_s + 1) + (g_e - g_s + 1) - inter
            iou = inter / union if union > 0 else 0.0
            peak_dist = abs(d_peak - g_peak)

            peak_valid = (peak_dist <= t_peak)
            overlap_valid = (iou >= 0.40)

            if peak_valid and overlap_valid:
                score = iou * 100.0 - float(peak_dist)
                candidate_matches.append((score, iou, g_idx, d, g))

    candidate_matches.sort(key=lambda x: (x[0], x[1]), reverse=True)

    matched_gt_indices: set = set()
    matched_detection_ids: set = set()
    matched_pairs: List[Dict[str, Any]] = []
    duplicate_detections: List[Dict[str, Any]] = []

    for score, iou, g_idx, d, g in candidate_matches:
        if d.finding_id in matched_detection_ids:
            continue
        if g_idx not in matched_gt_indices:
            matched_gt_indices.add(g_idx)
            matched_detection_ids.add(d.finding_id)
            d_mid = d.peak_frame if d.peak_frame is not None else int(round((d.frame_start + d.frame_end) / 2.0))
            g_mid = g.get("peak_frame", int(round((g.get("frames_0_based", [0, 0])[0] + g.get("frames_0_based", [0, 0])[1]) / 2.0)))
            matched_pairs.append({
                "detection_id": d.finding_id,
                "joint": d.affected_joint,
                "detection_interval": [d.frame_start, d.frame_end],
                "gt_interval": g.get("frames_0_based"),
                "iou": round(iou, 4),
                "peak_distance": abs(d_mid - g_mid),
                "verdict": d.verdict.value if d.verdict and hasattr(d.verdict, "value") else str(d.verdict),
                "finding": d,
                "gt": g,
            })
        else:
            matched_detection_ids.add(d.finding_id)
            duplicate_detections.append({
                "detection_id": d.finding_id,
                "joint": d.affected_joint,
                "interval": [d.frame_start, d.frame_end],
                "target_gt_index": g_idx,
            })

    unmatched_gt = [
        g for idx, g in enumerate(gt_defective)
        if idx not in matched_gt_indices
    ]
    unmatched_detections = [
        {
            "detection_id": d.finding_id,
            "joint": d.affected_joint,
            "interval": [d.frame_start, d.frame_end],
            "verdict": d.verdict.value if d.verdict and hasattr(d.verdict, "value") else str(d.verdict),
        }
        for d in findings
        if d.finding_id not in matched_detection_ids
    ]

    total_excess_good_frames = 0
    for d in findings:
        j_acc = acceptable_map.get(d.affected_joint, [])
        for f in range(d.frame_start, d.frame_end + 1):
            if any(acc[0] <= f <= acc[1] for acc in j_acc):
                total_excess_good_frames += 1

    total_excess_width = 0
    for pair in matched_pairs:
        d = pair["finding"]
        g = pair["gt"]
        g_s, g_e = g.get("frames_0_based", [0, 0])
        j_unc = uncertain_map.get(d.affected_joint, [])
        for f in range(d.frame_start, d.frame_end + 1):
            if not (g_s <= f <= g_e) and not any(u[0] <= f <= u[1] for u in j_unc):
                total_excess_width += 1

    total_gt = len(gt_defective)
    if total_gt == 0:
        confirmed_recall = 1.0 if len(findings) == 0 else 0.0
        review_recall = 1.0 if len(findings) == 0 else 0.0
        frame_cov = 1.0
    else:
        confirmed_count = sum(
            1 for p in matched_pairs
            if p["finding"].verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT
        )
        review_count = sum(
            1 for p in matched_pairs
            if p["finding"].verdict in (AssessmentVerdict.LIKELY_VISIBLE_DEFECT, AssessmentVerdict.REVIEW)
        )
        confirmed_recall = round(confirmed_count / total_gt, 4)
        review_recall = round(review_count / total_gt, 4)

        all_gt_frames = set()
        for g in gt_defective:
            s, e = g.get("frames_0_based", [0, 0])
            all_gt_frames.update(range(s, e + 1))
        covered_frames = set()
        for p in matched_pairs:
            d = p["finding"]
            covered_frames.update(
                f for f in range(d.frame_start, d.frame_end + 1)
                if f in all_gt_frames
            )
        frame_cov = round(len(covered_frames) / max(1, len(all_gt_frames)), 4)

    if not findings and total_gt == 0:
        joint_acc = 1.0
    elif not findings:
        joint_acc = 0.0
    else:
        correct_originating = sum(
            1 for d in findings
            if (originating_joints and d.affected_joint in originating_joints) or
               (not originating_joints and any(d.affected_joint == g.get("joint") for g in gt_defective))
        )
        joint_acc = round(correct_originating / len(findings), 4)

    return EventMatchResult(
        clip_name=clip_name,
        total_gt_events=total_gt,
        matched_gt_events=len(matched_gt_indices),
        confirmed_recall=confirmed_recall,
        review_inclusive_recall=review_recall,
        defective_frame_coverage=frame_cov,
        excess_good_frames_flagged=total_excess_good_frames,
        joint_attribution_accuracy=joint_acc,
        duplicate_penalties=len(duplicate_detections),
        excess_width_penalties=total_excess_width,
        matched_pairs=[
            {k: v for k, v in p.items() if k not in ("finding", "gt")}
            for p in matched_pairs
        ],
        unmatched_gt=unmatched_gt,
        unmatched_detections=unmatched_detections,
        duplicate_detections=duplicate_detections,
    )


class DiagnosticSummary(str):
    summary: str
    structured_metadata: List[Dict[str, Any]]

    def __new__(cls, summary: str, structured_metadata: Optional[List[Dict[str, Any]]] = None):
        obj = super().__new__(cls, summary)
        obj.summary = summary
        obj.structured_metadata = structured_metadata or []
        return obj

    def __iter__(self):
        return iter((self.summary, self.structured_metadata))


def generate_diagnostic_summary(analysis: Analysis, metadata: Optional[BVHMetadata] = None) -> DiagnosticSummary:
    frame_count = metadata.frame_count if metadata else (max((f.frame_end for f in analysis.findings), default=0) if analysis.findings else 0)
    duration_seconds = metadata.duration_seconds if metadata else (max((f.time_end for f in analysis.findings), default=0.0) if analysis.findings else 0.0)

    structured_metadata: List[Dict[str, Any]] = [
        {
            "finding_id": f.finding_id,
            "joint": f.affected_joint,
            "affected_body_part": f.affected_body_part.value if hasattr(f.affected_body_part, "value") else str(f.affected_body_part),
            "frame_start": f.frame_start,
            "frame_end": f.frame_end,
            "time_start": f.time_start,
            "time_end": f.time_end,
            "anomaly_type": f.anomaly_type.value if hasattr(f.anomaly_type, "value") else str(f.anomaly_type),
            "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
            "confidence": f.confidence,
            "explanation": f.explanation,
        }
        for f in analysis.findings
    ]

    if analysis.status == AnalysisStatus.CLEAN or (not analysis.findings and analysis.status != AnalysisStatus.INCONCLUSIVE):
        summary_text = f"Kinematic analysis complete: No jitter, foot sliding, or root discontinuities detected across {frame_count} frames ({duration_seconds:.2f}s). Ready for retargeting or export."
        return DiagnosticSummary(summary_text, structured_metadata)

    if analysis.status == AnalysisStatus.INCONCLUSIVE and not analysis.findings:
        summary_text = f"Kinematic analysis inconclusive: Skeleton geometry or scale could not be reliably verified across {frame_count} frames ({duration_seconds:.2f}s)."
        return DiagnosticSummary(summary_text, structured_metadata)

    unique_joints = sorted(list(set(f.affected_joint for f in analysis.findings)))
    joint_str = "joints" if len(unique_joints) != 1 else "joint"
    anomaly_str = "anomalies" if len(analysis.findings) != 1 else "anomaly"
    lines = [
        f"Kinematic analysis detected {len(analysis.findings)} {anomaly_str} across {len(unique_joints)} {joint_str} ({frame_count} frames, {duration_seconds:.2f}s):"
    ]
    for f in analysis.findings:
        lines.append(
            f"- {f.affected_joint}: frames {f.frame_start}-{f.frame_end} ({f.anomaly_type.value if hasattr(f.anomaly_type, 'value') else f.anomaly_type}, {f.severity.value if hasattr(f.severity, 'value') else f.severity}) - {f.explanation}"
        )
    summary_text = "\n".join(lines)
    return DiagnosticSummary(summary_text, structured_metadata)


def analyze_bvh_monolithic(
    parsed: ParsedBVH,
    asset_id: str,
    created_at: str,
    include_all_verdicts: bool = False,
    whole_clip_stats: Optional[WholeClipStatistics] = None,
) -> Analysis:
    metadata = parsed.metadata
    rep = SharedMotionRepresentation(parsed, normalize_coordinates=True)
    up_axis = rep.detected_up_axis
    detector_status: Dict[str, str] = {}
    findings: List[Finding] = []

    if metadata.frame_count <= 2:
        detector_status = {
            "rotation_jitter": "INCONCLUSIVE",
            "translation_jitter": "INCONCLUSIVE",
            "root_discontinuity": "INCONCLUSIVE",
            "foot_contact": "INCONCLUSIVE",
            "file_syntax": "COMPLETED",
            "sensor_tracking": "INCONCLUSIVE",
            "representation_singularities": "INCONCLUSIVE",
            "biomechanical_rom": "INCONCLUSIVE",
            "environmental_contact": "INCONCLUSIVE",
            "volumetric_collision": "INCONCLUSIVE",
            "physical_dynamics": "INCONCLUSIVE",
            "motion_pops": "INCONCLUSIVE",
        }
        analysis_id = hashlib.sha256(f"{asset_id}:analysis".encode("utf-8")).hexdigest()[:16]
        analysis_hash = compute_analysis_hash(
            parsed.raw_content_hash,
            metadata.skeleton_signature,
            metadata.parser_version,
            DETECTOR_VERSION,
            [],
        )
        analysis_obj = Analysis(
            analysis_id=analysis_id,
            asset_id=asset_id,
            content_hash=parsed.raw_content_hash,
            skeleton_signature=metadata.skeleton_signature,
            parser_version=metadata.parser_version,
            detector_version=DETECTOR_VERSION,
            analysis_hash=analysis_hash,
            status=AnalysisStatus.INCONCLUSIVE,
            up_axis=up_axis,
            findings=[],
            detector_status=detector_status,
            diagnostic_summary=None,
            created_at=created_at,
        )
        analysis_obj.diagnostic_summary = generate_diagnostic_summary(analysis_obj, metadata)
        return analysis_obj

    scale_valid = metadata.skeleton_scale > 0.0 and math.isfinite(metadata.skeleton_scale)

    detector_status["file_syntax"] = "COMPLETED"

    rot_findings = detect_rotation_jitter(parsed, metadata, whole_clip_stats=whole_clip_stats)
    findings.extend(rot_findings)
    detector_status["rotation_jitter"] = "COMPLETED"

    singularity_findings = detect_representation_singularities(parsed, metadata)
    findings.extend(singularity_findings)
    detector_status["representation_singularities"] = "COMPLETED"

    if scale_valid:
        root_findings = detect_root_discontinuity(parsed, metadata, whole_clip_stats=whole_clip_stats)
        findings.extend(root_findings)
        detector_status["root_discontinuity"] = "COMPLETED"

        trans_findings = detect_translation_jitter(parsed, metadata, whole_clip_stats=whole_clip_stats)
        findings.extend(trans_findings)
        detector_status["translation_jitter"] = "COMPLETED"
    else:
        detector_status["root_discontinuity"] = "INCONCLUSIVE"
        detector_status["translation_jitter"] = "INCONCLUSIVE"

    if not scale_valid:
        detector_status["foot_contact"] = "INCONCLUSIVE"
        detector_status["sensor_tracking"] = "INCONCLUSIVE"
        detector_status["biomechanical_rom"] = "INCONCLUSIVE"
        detector_status["environmental_contact"] = "INCONCLUSIVE"
        detector_status["volumetric_collision"] = "INCONCLUSIVE"
        detector_status["physical_dynamics"] = "INCONCLUSIVE"
    else:
        joint_positions = rep.world_positions

        sensor_findings = detect_sensor_tracking_artifacts(parsed, metadata, joint_positions, whole_clip_stats=whole_clip_stats)
        findings.extend(sensor_findings)
        detector_status["sensor_tracking"] = "COMPLETED"

        bio_findings = detect_biomechanical_violations(parsed, metadata, joint_positions)
        findings.extend(bio_findings)
        detector_status["biomechanical_rom"] = "COMPLETED"

        contact_findings, contact_evaluated = detect_contact_and_ground(parsed, metadata, joint_positions, whole_clip_stats=whole_clip_stats)
        if contact_evaluated:
            findings.extend(contact_findings)
            detector_status["foot_contact"] = "COMPLETED"
            detector_status["environmental_contact"] = "COMPLETED"
        else:
            detector_status["foot_contact"] = "INCONCLUSIVE"
            detector_status["environmental_contact"] = "INCONCLUSIVE"

        collision_findings = detect_volumetric_self_collisions(parsed, metadata, joint_positions)
        findings.extend(collision_findings)
        detector_status["volumetric_collision"] = "COMPLETED"

        dyn_findings = detect_physical_dynamics(parsed, metadata, joint_positions, whole_clip_stats=whole_clip_stats)
        findings.extend(dyn_findings)
        detector_status["physical_dynamics"] = "COMPLETED"

        pop_findings = detect_motion_pops(parsed, metadata, rep=rep, include_all_verdicts=include_all_verdicts, whole_clip_stats=whole_clip_stats)
        findings.extend(pop_findings)
        detector_status["motion_pops"] = "COMPLETED"

    for f in findings:
        if not f.created_at:
            f.created_at = created_at
        if f.verdict is None:
            if f.severity in (Severity.HIGH, Severity.CRITICAL) and f.confidence >= 0.8:
                f.verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
            elif f.severity == Severity.LOW or f.confidence < 0.6:
                f.verdict = AssessmentVerdict.NUMERICAL_ONLY
            else:
                f.verdict = AssessmentVerdict.REVIEW

    if not include_all_verdicts:
        findings = [
            f for f in findings
            if f.verdict in (AssessmentVerdict.LIKELY_VISIBLE_DEFECT, AssessmentVerdict.REVIEW)
        ]

    if findings:
        status = AnalysisStatus.FINDINGS
    elif not scale_valid:
        status = AnalysisStatus.INCONCLUSIVE
    elif detector_status.get("biomechanical_rom") == "INCONCLUSIVE" or detector_status.get("sensor_tracking") == "INCONCLUSIVE":
        status = AnalysisStatus.INCONCLUSIVE
    else:
        status = AnalysisStatus.CLEAN

    findings.sort(key=lambda f: (f.frame_start, f.frame_end, f.affected_joint, f.finding_id))

    analysis_id = hashlib.sha256(f"{asset_id}:analysis".encode("utf-8")).hexdigest()[:16]
    analysis_hash = compute_analysis_hash(
        parsed.raw_content_hash,
        metadata.skeleton_signature,
        metadata.parser_version,
        DETECTOR_VERSION,
        findings,
    )

    analysis_obj = Analysis(
        analysis_id=analysis_id,
        asset_id=asset_id,
        content_hash=parsed.raw_content_hash,
        skeleton_signature=metadata.skeleton_signature,
        parser_version=metadata.parser_version,
        detector_version=DETECTOR_VERSION,
        analysis_hash=analysis_hash,
        status=status,
        up_axis=up_axis,
        findings=findings,
        detector_status=detector_status,
        diagnostic_summary=None,
        created_at=created_at,
    )
    analysis_obj.diagnostic_summary = generate_diagnostic_summary(analysis_obj, metadata)
    return analysis_obj


def analyze_bvh_chunked(
    parsed: ParsedBVH,
    asset_id: str,
    created_at: str,
    include_all_verdicts: bool = False,
    chunk_size: int = 1000,
    overlap_frames: int = 120,
) -> Analysis:
    fc = parsed.metadata.frame_count
    dt = parsed.metadata.frame_time
    scale = parsed.metadata.skeleton_scale
    scale_valid = scale > 0.0 and math.isfinite(scale)

    if fc <= 2 or fc <= chunk_size:
        return analyze_bvh_monolithic(
            parsed,
            asset_id=asset_id,
            created_at=created_at,
            include_all_verdicts=include_all_verdicts,
        )

    whole_clip_stats = extract_whole_clip_statistics(parsed)
    raw_findings: List[Finding] = []

    k = 0
    while True:
        core_start = k * chunk_size
        core_end = min(fc, (k + 1) * chunk_size)
        if core_start >= fc:
            break
        ext_start = max(0, core_start - overlap_frames)
        ext_end = min(fc, core_end + overlap_frames)

        chunk_bvh = slice_parsed_bvh(parsed, ext_start, ext_end)
        chunk_analysis = analyze_bvh_monolithic(
            chunk_bvh,
            asset_id=asset_id,
            created_at=created_at,
            include_all_verdicts=True,
            whole_clip_stats=whole_clip_stats,
        )

        for f in chunk_analysis.findings:
            g_start = ext_start + f.frame_start
            g_end = ext_start + f.frame_end
            if g_end < core_start + 1 or g_start > core_end:
                continue

            ev = copy.deepcopy(f.evidence)
            if "peak_frame" in ev and isinstance(ev["peak_frame"], int):
                ev["peak_frame"] = ext_start + ev["peak_frame"]
            if "display_peak_frame" in ev and isinstance(ev["display_peak_frame"], int):
                ev["display_peak_frame"] = ext_start + ev["display_peak_frame"]
            if "playback_frame_start" in ev and isinstance(ev["playback_frame_start"], int):
                ev["playback_frame_start"] = ext_start + ev["playback_frame_start"]
            if "playback_frame_end" in ev and isinstance(ev["playback_frame_end"], int):
                ev["playback_frame_end"] = ext_start + ev["playback_frame_end"]
            if "display_playback_frame_start" in ev and isinstance(ev["display_playback_frame_start"], int):
                ev["display_playback_frame_start"] = ext_start + ev["display_playback_frame_start"]
            if "display_playback_frame_end" in ev and isinstance(ev["display_playback_frame_end"], int):
                ev["display_playback_frame_end"] = ext_start + ev["display_playback_frame_end"]

            fid = generate_finding_id(f.anomaly_type, f.affected_joint, g_start, g_end, ev)
            g_f = Finding(
                finding_id=fid,
                affected_joint=f.affected_joint,
                affected_body_part=f.affected_body_part,
                frame_start=g_start,
                frame_end=g_end,
                time_start=round(f.time_start + ext_start * dt, 6),
                time_end=round(f.time_end + ext_start * dt, 6),
                anomaly_type=f.anomaly_type,
                severity=f.severity,
                confidence=f.confidence,
                verdict=f.verdict,
                evidence=ev,
                detector_version=f.detector_version,
                explanation=f.explanation,
                created_at=f.created_at or created_at,
            )
            raw_findings.append(g_f)
        k += 1

    merged_findings = merge_boundary_findings(raw_findings, dt)

    for f in merged_findings:
        if not f.created_at:
            f.created_at = created_at
        if f.verdict is None:
            if f.severity in (Severity.HIGH, Severity.CRITICAL) and f.confidence >= 0.8:
                f.verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
            elif f.severity == Severity.LOW or f.confidence < 0.6:
                f.verdict = AssessmentVerdict.NUMERICAL_ONLY
            else:
                f.verdict = AssessmentVerdict.REVIEW

    if not include_all_verdicts:
        merged_findings = [
            f for f in merged_findings
            if f.verdict in (AssessmentVerdict.LIKELY_VISIBLE_DEFECT, AssessmentVerdict.REVIEW)
        ]

    merged_findings.sort(key=lambda f: (f.frame_start, f.frame_end, f.affected_joint, f.finding_id))

    detector_status = {
        "file_syntax": "COMPLETED",
        "rotation_jitter": "COMPLETED",
        "representation_singularities": "COMPLETED",
        "root_discontinuity": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "translation_jitter": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "sensor_tracking": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "biomechanical_rom": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "foot_contact": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "environmental_contact": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "volumetric_collision": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "physical_dynamics": "COMPLETED" if scale_valid else "INCONCLUSIVE",
        "motion_pops": "COMPLETED" if scale_valid else "INCONCLUSIVE",
    }

    if merged_findings:
        status = AnalysisStatus.FINDINGS
    elif not scale_valid:
        status = AnalysisStatus.INCONCLUSIVE
    else:
        status = AnalysisStatus.CLEAN

    up_axis = detect_coordinate_profile(parsed)
    if up_axis not in ("Y", "Z"):
        up_axis = parsed.metadata.up_axis or "Y"

    analysis_id = hashlib.sha256(f"{asset_id}:analysis".encode("utf-8")).hexdigest()[:16]
    analysis_hash = compute_analysis_hash(
        parsed.raw_content_hash,
        parsed.metadata.skeleton_signature,
        parsed.metadata.parser_version,
        DETECTOR_VERSION,
        merged_findings,
    )

    analysis_obj = Analysis(
        analysis_id=analysis_id,
        asset_id=asset_id,
        content_hash=parsed.raw_content_hash,
        skeleton_signature=parsed.metadata.skeleton_signature,
        parser_version=parsed.metadata.parser_version,
        detector_version=DETECTOR_VERSION,
        analysis_hash=analysis_hash,
        status=status,
        up_axis=up_axis,
        findings=merged_findings,
        detector_status=detector_status,
        diagnostic_summary=None,
        created_at=created_at,
    )
    analysis_obj.diagnostic_summary = generate_diagnostic_summary(analysis_obj, parsed.metadata)
    return analysis_obj


def analyze_bvh(
    parsed: ParsedBVH,
    asset_id: str,
    created_at: str,
    include_all_verdicts: bool = False,
    chunk_size: Optional[int] = None,
    overlap_frames: int = 120,
) -> Analysis:
    if chunk_size is not None:
        return analyze_bvh_chunked(
            parsed,
            asset_id,
            created_at,
            include_all_verdicts=include_all_verdicts,
            chunk_size=chunk_size,
            overlap_frames=overlap_frames,
        )
    if parsed.metadata.frame_count > 1500:
        return analyze_bvh_chunked(
            parsed,
            asset_id,
            created_at,
            include_all_verdicts=include_all_verdicts,
            chunk_size=1000,
            overlap_frames=overlap_frames,
        )
    return analyze_bvh_monolithic(
        parsed,
        asset_id,
        created_at,
        include_all_verdicts=include_all_verdicts,
    )

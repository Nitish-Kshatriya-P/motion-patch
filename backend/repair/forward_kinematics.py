import math
from typing import Dict, List, Tuple, Optional, Any
from bvh_parser import ParsedBVH, JointNode, BVHMetadata

class KinematicsError(ValueError):
    pass

def rotation_matrix_x(deg: float) -> List[List[float]]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]

def rotation_matrix_y(deg: float) -> List[List[float]]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]

def rotation_matrix_z(deg: float) -> List[List[float]]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]

def mat_mul_3x3(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [
        [
            a[r][0] * b[0][c] + a[r][1] * b[1][c] + a[r][2] * b[2][c]
            for c in range(3)
        ]
        for r in range(3)
    ]

def mat_vec_mul_3x3(m: List[List[float]], v: List[float]) -> List[float]:
    return [
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    ]

def vec_add(a: List[float], b: List[float]) -> List[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]

def identity_matrix_3x3() -> List[List[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

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

class ForwardKinematicsEngine:
    @staticmethod
    def validate_up_axis(parsed: ParsedBVH) -> None:
        root_ch = parsed.root_node.channels
        pos_ch = [c for c in root_ch if "position" in c.lower()]
        if "Yposition" not in pos_ch:
            raise KinematicsError("UNSUPPORTED_UP_AXIS")

    @staticmethod
    def create_motion_view(parsed: ParsedBVH, motion: List[List[float]]) -> ParsedBVH:
        fc = len(motion)
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
            motion=motion,
            metadata=meta,
            raw_content_hash=parsed.raw_content_hash,
        )

    @staticmethod
    def compute_joint_world_positions_for_motion(parsed: ParsedBVH, motion: List[List[float]]) -> Dict[str, List[List[float]]]:
        all_names = [j.name for j in parsed.ordered_joints]
        for j in parsed.ordered_joints:
            for child in j.children:
                if child.is_end_site and child.name not in all_names:
                    all_names.append(child.name)

        world_positions: Dict[str, List[List[float]]] = {name: [] for name in all_names}
        root = parsed.root_node

        for frame_motion in motion:
            rx, ry, rz = 0.0, 0.0, 0.0
            for ch_name, ch_idx in zip(root.channels, root.channel_indices):
                if ch_name == "Xposition":
                    rx = frame_motion[ch_idx]
                elif ch_name == "Yposition":
                    ry = frame_motion[ch_idx]
                elif ch_name == "Zposition":
                    rz = frame_motion[ch_idx]
            root_pos = [root.offset[0] + rx, root.offset[1] + ry, root.offset[2] + rz]
            root_rot = compute_joint_rotation_matrix(root, frame_motion)

            world_positions[root.name].append(root_pos)

            def propagate(node: JointNode, p_pos: List[float], p_rot: List[List[float]]):
                for child in node.children:
                    if child.is_end_site:
                        end_pos = vec_add(p_pos, mat_vec_mul_3x3(p_rot, child.offset))
                        world_positions[child.name].append(end_pos)
                        continue

                    cx, cy, cz = 0.0, 0.0, 0.0
                    for ch_name, ch_idx in zip(child.channels, child.channel_indices):
                        if ch_name == "Xposition":
                            cx = frame_motion[ch_idx]
                        elif ch_name == "Yposition":
                            cy = frame_motion[ch_idx]
                        elif ch_name == "Zposition":
                            cz = frame_motion[ch_idx]
                    c_local_pos = [child.offset[0] + cx, child.offset[1] + cy, child.offset[2] + cz]
                    c_local_rot = compute_joint_rotation_matrix(child, frame_motion)

                    child_pos = vec_add(p_pos, mat_vec_mul_3x3(p_rot, c_local_pos))
                    child_rot = mat_mul_3x3(p_rot, c_local_rot)
                    world_positions[child.name].append(child_pos)
                    propagate(child, child_pos, child_rot)

            propagate(root, root_pos, root_rot)

        return world_positions

    @staticmethod
    def derive_ground_floor(parsed: ParsedBVH, world_positions: Dict[str, List[List[float]]]) -> float:
        contact_joint_names = [j for j in world_positions.keys() if any(k in j.lower() for k in ("foot", "toe", "ankle", "heel"))]
        if not contact_joint_names:
            raise KinematicsError("FLOOR_ESTIMATION_UNCERTAIN")

        dt = parsed.metadata.frame_time
        fc = len(next(iter(world_positions.values())))
        scale = max(1.0, parsed.metadata.skeleton_scale)
        contact_speed_limit = 0.05 * scale
        sampled_y = []

        for j_name in contact_joint_names:
            pos_list = world_positions[j_name]
            for t in range(1, fc):
                prev_p = pos_list[t - 1]
                curr_p = pos_list[t]
                speed = math.sqrt((curr_p[0] - prev_p[0])**2 + (curr_p[1] - prev_p[1])**2 + (curr_p[2] - prev_p[2])**2) / dt
                if speed < contact_speed_limit:
                    sampled_y.append(curr_p[1])

        if len(sampled_y) < 10:
            raise KinematicsError("FLOOR_ESTIMATION_UNCERTAIN")

        sampled_y.sort()
        lowest_10_percent_idx = max(1, int(len(sampled_y) * 0.10))
        lowest_samples = sampled_y[:lowest_10_percent_idx]
        median_floor = lowest_samples[int(len(lowest_samples) / 2)]
        return median_floor

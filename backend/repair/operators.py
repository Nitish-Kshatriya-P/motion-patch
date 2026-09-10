import math
from typing import Dict, Tuple, List, Optional, Any
from bvh_parser import ParsedBVH, JointNode
from models import AnomalyType, Finding
from repair.contracts import WriteSetDeclaration, CandidateParameters
from repair.rotations import (
    euler_to_quaternion,
    quaternion_to_euler,
    select_closest_euler,
    slerp,
    quaternion_angular_distance,
)
from repair.forward_kinematics import ForwardKinematicsEngine

def evaluate_defect_improvement(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    finding: Finding,
    floor_y: float,
) -> Tuple[bool, Optional[str]]:
    f_start = finding.frame_start
    f_end = finding.frame_end
    dt = orig_parsed.metadata.frame_time
    scale = max(1.0, orig_parsed.metadata.skeleton_scale)

    if finding.anomaly_type == AnomalyType.ROOT_DISCONTINUITY:
        peak = finding.peak_frame if finding.peak_frame is not None else f_start
        root = orig_parsed.root_node
        pos_ch = [root.channel_indices[i] for i, c in enumerate(root.channels) if "position" in c.lower()]
        if not pos_ch:
            return True, None
        orig_jump = math.sqrt(sum((orig_parsed.motion[peak][c] - orig_parsed.motion[peak - 1][c])**2 for c in pos_ch))
        rep_jump = math.sqrt(sum((rep_parsed.motion[peak][c] - rep_parsed.motion[peak - 1][c])**2 for c in pos_ch))
        if rep_jump > max(0.05 * scale, 0.5 * orig_jump):
            return False, f"Root jump magnitude {rep_jump:.4f} not sufficiently reduced from {orig_jump:.4f}"
        return True, None

    elif finding.anomaly_type == AnomalyType.OPTICAL_OCCLUSION_FLATLINE:
        joint_name = finding.affected_joint
        joint = orig_parsed.joint_map.get(joint_name)
        if not joint:
            return True, None
        rep_vals = [rep_parsed.motion[t][joint.channel_indices[0]] for t in range(f_start, f_end + 1)]
        mean_v = sum(rep_vals) / len(rep_vals)
        variance = sum((v - mean_v)**2 for v in rep_vals) / len(rep_vals)
        if variance < 1e-5:
            return False, f"Freeze region motion flatline persisted with variance {variance:.6f}"
        return True, None

    elif finding.anomaly_type in (AnomalyType.EULER_GIMBAL_LOCK_FLIP, AnomalyType.OPTICAL_MARKER_SWAP):
        joint_name = finding.affected_joint
        joint = orig_parsed.joint_map.get(joint_name)
        if not joint or not joint.rotation_order:
            return True, None
        rot_indices = [joint.channel_indices[joint.channels.index(c)] for c in joint.rotation_order]
        peak = finding.peak_frame if finding.peak_frame is not None else int((f_start + f_end) / 2)
        if peak < 1 or peak >= orig_parsed.metadata.frame_count - 1:
            return True, None

        q0_orig = euler_to_quaternion([orig_parsed.motion[peak - 1][idx] for idx in rot_indices], joint.rotation_order)
        q1_orig = euler_to_quaternion([orig_parsed.motion[peak][idx] for idx in rot_indices], joint.rotation_order)
        q2_orig = euler_to_quaternion([orig_parsed.motion[peak + 1][idx] for idx in rot_indices], joint.rotation_order)
        acc_orig = abs(quaternion_angular_distance(q1_orig, q2_orig) - quaternion_angular_distance(q0_orig, q1_orig))

        q0_rep = euler_to_quaternion([rep_parsed.motion[peak - 1][idx] for idx in rot_indices], joint.rotation_order)
        q1_rep = euler_to_quaternion([rep_parsed.motion[peak][idx] for idx in rot_indices], joint.rotation_order)
        q2_rep = euler_to_quaternion([rep_parsed.motion[peak + 1][idx] for idx in rot_indices], joint.rotation_order)
        acc_rep = abs(quaternion_angular_distance(q1_rep, q2_rep) - quaternion_angular_distance(q0_rep, q1_rep))

        if acc_rep > 0.6 * acc_orig:
            return False, f"Angular acceleration spike {acc_rep:.2f} not reduced by >= 40% from {acc_orig:.2f}"
        return True, None

    elif finding.anomaly_type in (AnomalyType.ROTATION_JITTER, AnomalyType.TRANSLATION_JITTER):
        joint_name = finding.affected_joint
        joint = orig_parsed.joint_map.get(joint_name)
        if not joint:
            return True, None
        target_ch = joint.channel_indices[0]
        orig_diffs = [abs(orig_parsed.motion[t][target_ch] - orig_parsed.motion[t - 1][target_ch]) for t in range(f_start + 1, f_end + 1)]
        rep_diffs = [abs(rep_parsed.motion[t][target_ch] - rep_parsed.motion[t - 1][target_ch]) for t in range(f_start + 1, f_end + 1)]
        orig_energy = sum(orig_diffs)
        rep_energy = sum(rep_diffs)
        if orig_energy > 1e-4 and rep_energy > 0.85 * orig_energy:
            return False, f"Jitter energy {rep_energy:.4f} not reduced by >= 15% from {orig_energy:.4f}"
        return True, None

    elif finding.anomaly_type == AnomalyType.GROUND_PENETRATION:
        rep_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(rep_parsed, rep_parsed.motion)
        orig_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(orig_parsed, orig_parsed.motion)
        contact_joints = [j for j in rep_world_pos.keys() if any(k in j.lower() for k in ("foot", "toe", "ankle", "heel"))]
        if not contact_joints:
            return True, None

        min_rep_y = min(min(rep_world_pos[j][t][1] for t in range(f_start, f_end + 1)) for j in contact_joints)
        min_orig_y = min(min(orig_world_pos[j][t][1] for t in range(f_start, f_end + 1)) for j in contact_joints)

        if min_rep_y < min_orig_y - 1e-4:
            return False, f"Ground penetration worsened: rep min Y {min_rep_y:.4f} < orig min Y {min_orig_y:.4f}"
        if min_orig_y < floor_y and min_rep_y < floor_y - 0.01 * scale:
            if (min_rep_y - min_orig_y) < 0.2 * (floor_y - min_orig_y):
                return False, f"Ground penetration insufficiently corrected: rep min Y {min_rep_y:.4f}"
        return True, None

    elif finding.anomaly_type == AnomalyType.PLANTED_FOOT_SLIDING:
        rep_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(rep_parsed, rep_parsed.motion)
        orig_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(orig_parsed, orig_parsed.motion)
        j_name = finding.affected_joint
        if j_name not in rep_world_pos:
            return True, None

        orig_drift = sum(math.sqrt((orig_world_pos[j_name][t][0] - orig_world_pos[j_name][t - 1][0])**2 + (orig_world_pos[j_name][t][2] - orig_world_pos[j_name][t - 1][2])**2) for t in range(f_start + 1, f_end + 1))
        rep_drift = sum(math.sqrt((rep_world_pos[j_name][t][0] - rep_world_pos[j_name][t - 1][0])**2 + (rep_world_pos[j_name][t][2] - rep_world_pos[j_name][t - 1][2])**2) for t in range(f_start + 1, f_end + 1))
        if orig_drift > 1e-4 and rep_drift > 0.7 * orig_drift:
            return False, f"Foot drift {rep_drift:.4f} not reduced by >= 30% from {orig_drift:.4f}"
        return True, None

    return True, None

class RepairOperatorEngine:
    @staticmethod
    def generate_candidate(
        parsed: ParsedBVH,
        working_motion: List[List[float]],
        finding: Finding,
        floor_y: float,
        candidate_params: CandidateParameters,
    ) -> Tuple[Dict[Tuple[int, int], float], List[WriteSetDeclaration]]:
        op_id = candidate_params.candidate_id
        f_start = finding.frame_start
        f_end = finding.frame_end
        fc = len(working_motion)
        modifications: Dict[Tuple[int, int], float] = {}
        write_sets: List[WriteSetDeclaration] = []

        if finding.anomaly_type == AnomalyType.ROOT_DISCONTINUITY:
            peak = finding.peak_frame if finding.peak_frame is not None else f_start
            root = parsed.root_node
            pos_channels = [c for c in root.channels if "position" in c.lower()]
            scale = max(1.0, parsed.metadata.skeleton_scale)

            for c_name in pos_channels:
                ch_idx = root.channel_indices[root.channels.index(c_name)]
                raw_diff = working_motion[peak][ch_idx] - working_motion[peak - 1][ch_idx]
                v_prev = (working_motion[peak - 1][ch_idx] - working_motion[peak - 2][ch_idx]) if peak >= 2 else 0.0
                step_delta = (raw_diff - v_prev) if candidate_params.candidate_id == "rj_offset_vprev" else raw_diff
                if abs(step_delta) < 0.02 * scale:
                    continue
                target_frames = list(range(peak, fc))
                max_change = abs(step_delta) * 1.5 + 0.1

                write_sets.append(
                    WriteSetDeclaration(
                        operator_id=op_id,
                        target_frames=target_frames,
                        joint_name=root.name,
                        channel_name=c_name,
                        channel_index=ch_idx,
                        max_permitted_change=max_change,
                        blend_frames=candidate_params.blend_frames,
                        derivation_reason=f"Root jump correction step {step_delta:.4f}",
                    )
                )

                for t in target_frames:
                    modifications[(t, ch_idx)] = working_motion[t][ch_idx] - step_delta

        elif finding.anomaly_type == AnomalyType.OPTICAL_OCCLUSION_FLATLINE:
            joint = parsed.joint_map.get(finding.affected_joint)
            if joint and joint.rotation_order:
                rot_indices = [joint.channel_indices[joint.channels.index(c)] for c in joint.rotation_order]
                lead_in = max(0, f_start - 1)
                lead_out = min(fc - 1, f_end + 1)
                span = max(1, lead_out - lead_in)

                q_start = euler_to_quaternion([working_motion[lead_in][idx] for idx in rot_indices], joint.rotation_order)
                q_end = euler_to_quaternion([working_motion[lead_out][idx] for idx in rot_indices], joint.rotation_order)

                target_frames = list(range(f_start, f_end + 1))
                for c_name, c_idx in zip(joint.rotation_order, rot_indices):
                    write_sets.append(
                        WriteSetDeclaration(
                            operator_id=op_id,
                            target_frames=target_frames,
                            joint_name=joint.name,
                            channel_name=f"{c_name}rotation",
                            channel_index=c_idx,
                            max_permitted_change=180.0,
                            blend_frames=candidate_params.blend_frames,
                            derivation_reason="SLERP freeze interpolation",
                        )
                    )

                for t in target_frames:
                    u = (t - lead_in) / span
                    q_interp = slerp(q_start, q_end, u)
                    raw_euler = quaternion_to_euler(q_interp, joint.rotation_order)
                    closest_euler = select_closest_euler(raw_euler, [working_motion[t][idx] for idx in rot_indices])
                    for idx, e_val in zip(rot_indices, closest_euler):
                        modifications[(t, idx)] = e_val

        elif finding.anomaly_type in (AnomalyType.EULER_GIMBAL_LOCK_FLIP, AnomalyType.OPTICAL_MARKER_SWAP):
            joint = parsed.joint_map.get(finding.affected_joint)
            if joint and joint.rotation_order:
                rot_indices = [joint.channel_indices[joint.channels.index(c)] for c in joint.rotation_order]
                peak = finding.peak_frame if finding.peak_frame is not None else int((f_start + f_end) / 2)
                t0 = max(0, peak - 1)
                t1 = min(fc - 1, peak + 1)

                q0 = euler_to_quaternion([working_motion[t0][idx] for idx in rot_indices], joint.rotation_order)
                q1 = euler_to_quaternion([working_motion[t1][idx] for idx in rot_indices], joint.rotation_order)
                q_mid = slerp(q0, q1, 0.5)
                raw_euler = quaternion_to_euler(q_mid, joint.rotation_order)
                closest = select_closest_euler(raw_euler, [working_motion[t0][idx] for idx in rot_indices])

                for c_name, c_idx, val in zip(joint.rotation_order, rot_indices, closest):
                    write_sets.append(
                        WriteSetDeclaration(
                            operator_id=op_id,
                            target_frames=[peak],
                            joint_name=joint.name,
                            channel_name=f"{c_name}rotation",
                            channel_index=c_idx,
                            max_permitted_change=360.0,
                            blend_frames=1,
                            derivation_reason="Gimbal flip SLERP unwrap",
                        )
                    )
                    modifications[(peak, c_idx)] = val

        elif finding.anomaly_type in (AnomalyType.ROTATION_JITTER, AnomalyType.TRANSLATION_JITTER):
            joint = parsed.joint_map.get(finding.affected_joint)
            if joint:
                ch_indices = list(joint.channel_indices)
                target_frames = list(range(f_start, f_end + 1))
                W = candidate_params.smoothing_window

                for ch_idx in ch_indices:
                    ch_name = joint.channels[joint.channel_indices.index(ch_idx)]
                    write_sets.append(
                        WriteSetDeclaration(
                            operator_id=op_id,
                            target_frames=target_frames,
                            joint_name=joint.name,
                            channel_name=ch_name,
                            channel_index=ch_idx,
                            max_permitted_change=45.0 if "rotation" in ch_name.lower() else 5.0,
                            blend_frames=W,
                            derivation_reason="Windowed smoothing filter",
                        )
                    )

                    for t in target_frames:
                        win = [working_motion[k][ch_idx] for k in range(max(0, t - W), min(fc, t + W + 1))]
                        modifications[(t, ch_idx)] = sum(win) / len(win)

        elif finding.anomaly_type == AnomalyType.GROUND_PENETRATION:
            world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(parsed, working_motion)
            contact_joints = [j for j in world_pos.keys() if any(k in j.lower() for k in ("foot", "toe", "ankle", "heel"))]
            root = parsed.root_node
            y_indices = [root.channel_indices[i] for i, c in enumerate(root.channels) if c == "Yposition"]

            if contact_joints and y_indices:
                y_idx = y_indices[0]
                target_frames = list(range(f_start, f_end + 1))
                scale = max(1.0, parsed.metadata.skeleton_scale)

                penetrations = []
                for t in target_frames:
                    min_y = min(world_pos[j][t][1] for j in contact_joints)
                    pen = max(0.0, floor_y - min_y)
                    penetrations.append(pen)

                max_pen = max(penetrations) if penetrations else 0.0
                if max_pen > 0.0:
                    write_sets.append(
                        WriteSetDeclaration(
                            operator_id=op_id,
                            target_frames=target_frames,
                            joint_name=root.name,
                            channel_name="Yposition",
                            channel_index=y_idx,
                            max_permitted_change=max_pen * 1.5 + 0.05 * scale,
                            blend_frames=candidate_params.smoothing_window,
                            derivation_reason=f"Pelvis lift for ground penetration {max_pen:.4f}",
                        )
                    )

                    for t, pen in zip(target_frames, penetrations):
                        modifications[(t, y_idx)] = working_motion[t][y_idx] + pen

        elif finding.anomaly_type == AnomalyType.PLANTED_FOOT_SLIDING:
            joint = parsed.joint_map.get(finding.affected_joint)
            if joint:
                ch_indices = list(joint.channel_indices)
                target_frames = list(range(max(0, f_start), min(fc, f_end + 1)))
                ref_frame = max(0, f_start)
                for ch_idx in ch_indices:
                    ch_name = joint.channels[joint.channel_indices.index(ch_idx)]
                    write_sets.append(
                        WriteSetDeclaration(
                            operator_id=op_id,
                            target_frames=target_frames,
                            joint_name=joint.name,
                            channel_name=ch_name,
                            channel_index=ch_idx,
                            max_permitted_change=45.0 if "rotation" in ch_name.lower() else 5.0,
                            blend_frames=1,
                            derivation_reason="Foot plant lock stabilization",
                        )
                    )
                    ref_val = working_motion[ref_frame][ch_idx]
                    for t in target_frames:
                        if t != ref_frame:
                            modifications[(t, ch_idx)] = ref_val

        return modifications, write_sets

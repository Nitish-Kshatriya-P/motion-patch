import math
import os
from typing import Tuple, List, Dict, Any, Optional
from bvh_parser import parse_bvh_file, ParsedBVH
from models import AnomalyType, Finding
from repair.contracts import TokenReplacement, WriteSetDeclaration
from repair.token_patcher import TokenPatcher
from repair.scoring import GATE6_VELOCITY_CONFIG, GATE7_ROOT_CONFIG
from repair.rotations import quaternion_angular_distance, euler_to_quaternion
from repair.forward_kinematics import ForwardKinematicsEngine
from repair.operators import evaluate_defect_improvement

class ValidationPipeline:
    @staticmethod
    def run_production_gates(
        original_bvh_path: str,
        staging_bvh_path: str,
        orig_parsed: ParsedBVH,
        replacements: List[TokenReplacement],
        modifications: Dict[Tuple[int, int], float],
        write_sets: List[WriteSetDeclaration],
        finding: Finding,
        previously_satisfied_findings: List[Finding],
        floor_y: float,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            rep_parsed = parse_bvh_file(staging_bvh_path)
        except Exception as e:
            return False, "GATE_1_PARSING_FAILED", str(e)

        for r_idx, row in enumerate(rep_parsed.motion):
            for c_idx, val in enumerate(row):
                if math.isnan(val) or math.isinf(val):
                    return False, "GATE_1_NON_FINITE_TOKEN", f"Found non-finite token at row {r_idx} channel {c_idx}"

        if rep_parsed.metadata.total_channels != orig_parsed.metadata.total_channels:
            return False, "GATE_2_CHANNEL_COUNT_MISMATCH", "Channel count altered"
        if rep_parsed.metadata.frame_count != orig_parsed.metadata.frame_count:
            return False, "GATE_2_FRAME_COUNT_MISMATCH", "Frame count altered"
        if abs(rep_parsed.metadata.frame_time - orig_parsed.metadata.frame_time) > 1e-7:
            return False, "GATE_2_FRAME_TIME_MISMATCH", "Frame time altered"
        if rep_parsed.metadata.skeleton_signature != orig_parsed.metadata.skeleton_signature:
            return False, "GATE_2_SKELETON_SIGNATURE_MISMATCH", "Skeleton hierarchy altered"

        orig_names = [j.name for j in orig_parsed.ordered_joints]
        rep_names = [j.name for j in rep_parsed.ordered_joints]
        if orig_names != rep_names:
            return False, "GATE_2_JOINT_ORDER_MISMATCH", "Joint names or order altered"

        for j_orig, j_rep in zip(orig_parsed.ordered_joints, rep_parsed.ordered_joints):
            if j_orig.channels != j_rep.channels or j_orig.channel_indices != j_rep.channel_indices:
                return False, "GATE_2_CHANNEL_MAPPING_MISMATCH", f"Channel mapping for {j_orig.name} altered"

        with open(original_bvh_path, "rb") as f_orig, open(staging_bvh_path, "rb") as f_rep:
            orig_bytes = f_orig.read()
            rep_bytes = f_rep.read()
        byte_ok, byte_err = TokenPatcher.verify_ledger_byte_preservation(orig_bytes, rep_bytes, replacements)
        if not byte_ok:
            return False, "GATE_3_BYTE_PRESERVATION_FAILED", byte_err

        rep_keys = {(r.frame_index, r.channel_index) for r in replacements}
        mod_keys = set(modifications.keys())
        if rep_keys != mod_keys:
            return False, "GATE_3_REPLACEMENT_SET_MISMATCH", f"Replacements count {len(rep_keys)} != modifications count {len(mod_keys)}"

        for r in replacements:
            expected_v = round(modifications[(r.frame_index, r.channel_index)], 6)
            actual_v = float(r.output_token)
            if abs(actual_v - expected_v) > 1e-6:
                return False, "GATE_3_REPLACEMENT_VALUE_MISMATCH", f"Output token at ({r.frame_index}, {r.channel_index}) does not match rounded modification"

        write_set_lookup = {}
        for ws in write_sets:
            for f in ws.target_frames:
                key = (f, ws.channel_index)
                if key in write_set_lookup:
                    write_set_lookup[key] = min(write_set_lookup[key], ws.max_permitted_change)
                else:
                    write_set_lookup[key] = ws.max_permitted_change

        for rep in replacements:
            key = (rep.frame_index, rep.channel_index)
            if key not in write_set_lookup:
                return False, "GATE_4_UNAUTHORIZED_CHANNEL_MODIFIED", f"Token at {key} not declared in write-set"
            max_c = write_set_lookup[key]
            orig_v = float(rep.original_token)
            out_v = float(rep.output_token)
            if abs(out_v - orig_v) > max_c + 1e-4:
                return False, "GATE_4_MAX_PERMITTED_CHANGE_EXCEEDED", f"Token at {key} delta {abs(out_v - orig_v)} exceeds {max_c}"

        imp_ok, imp_err = evaluate_defect_improvement(orig_parsed, rep_parsed, finding, floor_y)
        if not imp_ok:
            return False, "GATE_5_DEFECT_IMPROVEMENT_FAILED", imp_err

        dt = orig_parsed.metadata.frame_time
        fc = rep_parsed.metadata.frame_count
        scale = max(1.0, orig_parsed.metadata.skeleton_scale)
        W = GATE6_VELOCITY_CONFIG["context_window"]
        mult = GATE6_VELOCITY_CONFIG["multiplier"]

        position_indices = set()
        rotation_indices = set()
        for joint in orig_parsed.ordered_joints:
            for channel_name, channel_index in zip(joint.channels, joint.channel_indices):
                if channel_name.endswith("position"):
                    position_indices.add(channel_index)
                elif channel_name.endswith("rotation"):
                    rotation_indices.add(channel_index)

        channel_frames: Dict[int, Set[int]] = {}
        for ws in write_sets:
            for f in ws.target_frames:
                channel_frames.setdefault(ws.channel_index, set()).add(f)

        for ch, f_set in channel_frames.items():
            if not f_set:
                continue
            sorted_f = sorted(f_set)
            runs = []
            curr_start = sorted_f[0]
            curr_end = sorted_f[0]
            for f in sorted_f[1:]:
                if f == curr_end + 1:
                    curr_end = f
                else:
                    runs.append((curr_start, curr_end))
                    curr_start = f
                    curr_end = f
            runs.append((curr_start, curr_end))

            is_pos = ch in position_indices

            for f_start, f_end in runs:
                context_frames = []
                for t in range(max(1, f_start - W), f_start):
                    context_frames.append(t)
                for t in range(f_end + 1, min(fc, f_end + 1 + W)):
                    context_frames.append(t)

                clean_accels = []
                for t in context_frames:
                    if t >= 2:
                        v0 = (orig_parsed.motion[t - 1][ch] - orig_parsed.motion[t - 2][ch]) / dt
                        v1 = (orig_parsed.motion[t][ch] - orig_parsed.motion[t - 1][ch]) / dt
                        clean_accels.append(abs((v1 - v0) / dt))

                clean_accels.sort()
                med_accel = clean_accels[int(len(clean_accels) / 2)] if clean_accels else 1.0

                if is_pos:
                    limit = max(
                        GATE6_VELOCITY_CONFIG["pos_scale_floor_per_second"] * scale,
                        mult * med_accel * dt,
                    )
                else:
                    limit = max(
                        GATE6_VELOCITY_CONFIG["rot_scale_floor_deg_per_second"],
                        mult * med_accel * dt,
                    )

                if f_start > 1:
                    v_pre = (rep_parsed.motion[f_start - 1][ch] - rep_parsed.motion[f_start - 2][ch]) / dt
                    v_post = (rep_parsed.motion[f_start][ch] - rep_parsed.motion[f_start - 1][ch]) / dt
                    if abs(v_post - v_pre) > limit:
                        return False, "GATE_6_BOUNDARY_VELOCITY_DISCONTINUOUS", f"Lead-in boundary velocity step {abs(v_post - v_pre):.4f} exceeds limit {limit:.4f}"

                if f_end < fc - 2:
                    v_pre = (rep_parsed.motion[f_end][ch] - rep_parsed.motion[f_end - 1][ch]) / dt
                    v_post = (rep_parsed.motion[f_end + 1][ch] - rep_parsed.motion[f_end][ch]) / dt
                    if abs(v_post - v_pre) > limit:
                        return False, "GATE_6_BOUNDARY_VELOCITY_DISCONTINUOUS", f"Lead-out boundary velocity step {abs(v_post - v_pre):.4f} exceeds limit {limit:.4f}"

        max_deg_per_frame = 1500.0 * dt
        edited_channels = set(ws.channel_index for ws in write_sets)
        for joint in orig_parsed.ordered_joints:
            if not joint.rotation_order:
                continue
            rot_indices = [joint.channel_indices[joint.channels.index(c)] for c in joint.rotation_order]
            is_joint_edited = any(idx in edited_channels for idx in rot_indices)

            for t in range(fc - 1):
                e0_rep = [rep_parsed.motion[t][idx] for idx in rot_indices]
                e1_rep = [rep_parsed.motion[t + 1][idx] for idx in rot_indices]
                q0_rep = euler_to_quaternion(e0_rep, joint.rotation_order)
                q1_rep = euler_to_quaternion(e1_rep, joint.rotation_order)
                ang_dist_rep = quaternion_angular_distance(q0_rep, q1_rep)

                if not is_joint_edited:
                    e0_orig = [orig_parsed.motion[t][idx] for idx in rot_indices]
                    e1_orig = [orig_parsed.motion[t + 1][idx] for idx in rot_indices]
                    q0_orig = euler_to_quaternion(e0_orig, joint.rotation_order)
                    q1_orig = euler_to_quaternion(e1_orig, joint.rotation_order)
                    ang_dist_orig = quaternion_angular_distance(q0_orig, q1_orig)
                    if abs(ang_dist_rep - ang_dist_orig) > 1e-4:
                        return False, "GATE_6_UNMODIFIED_JOINT_ANGULAR_ALTERED", f"Unmodified joint {joint.name} at frame {t} altered"
                else:
                    e0_orig = [orig_parsed.motion[t][idx] for idx in rot_indices]
                    e1_orig = [orig_parsed.motion[t + 1][idx] for idx in rot_indices]
                    q0_orig = euler_to_quaternion(e0_orig, joint.rotation_order)
                    q1_orig = euler_to_quaternion(e1_orig, joint.rotation_order)
                    ang_dist_orig = quaternion_angular_distance(q0_orig, q1_orig)

                    if ang_dist_orig > max_deg_per_frame:
                        if ang_dist_rep > ang_dist_orig + 1e-4:
                            return False, "GATE_6_ANGULAR_VELOCITY_WORSENED", f"Joint {joint.name} frame {t} worsened elevated motion"
                    else:
                        if ang_dist_rep > max_deg_per_frame:
                            return False, "GATE_6_ANGULAR_VELOCITY_EXCEEDED", f"Joint {joint.name} frame {t} displacement {ang_dist_rep:.2f} exceeds limit {max_deg_per_frame:.2f}"

        orig_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(orig_parsed, orig_parsed.motion)
        rep_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(rep_parsed, rep_parsed.motion)
        contact_joint_names = [j for j in rep_world_pos.keys() if any(k in j.lower() for k in ("foot", "toe", "ankle", "heel"))]
        is_ground_repair = finding.anomaly_type == AnomalyType.GROUND_PENETRATION
        ground_frames = set(range(finding.frame_start, finding.frame_end + 1)) if is_ground_repair else set()

        for j_name in contact_joint_names:
            for t in range(fc):
                orig_y = orig_world_pos[j_name][t][1]
                rep_y = rep_world_pos[j_name][t][1]

                if t in ground_frames:
                    if rep_y < orig_y - 1e-4:
                        return False, "GATE_7_GROUND_REPAIR_REGRESSION", f"Ground repair worsened penetration on {j_name} at frame {t}"
                else:
                    if rep_y < floor_y and rep_y < orig_y - 1e-4:
                        return False, "GATE_7_FLOOR_PENETRATION_WORSENED", f"Joint {j_name} at frame {t} worsened pre-existing penetration"

        root = orig_parsed.root_node
        root_ch_map = {c: root.channel_indices[i] for i, c in enumerate(root.channels)}
        x_idx, y_idx, z_idx = root_ch_map.get("Xposition"), root_ch_map.get("Yposition"), root_ch_map.get("Zposition")

        if finding.anomaly_type == AnomalyType.GROUND_PENETRATION:
            for t in range(fc):
                if x_idx is not None and abs(rep_parsed.motion[t][x_idx] - orig_parsed.motion[t][x_idx]) > 1e-6:
                    return False, "GATE_7_ROOT_GROUND_XZ_DRIFT", f"Ground repair altered Xposition at frame {t}"
                if z_idx is not None and abs(rep_parsed.motion[t][z_idx] - orig_parsed.motion[t][z_idx]) > 1e-6:
                    return False, "GATE_7_ROOT_GROUND_XZ_DRIFT", f"Ground repair altered Zposition at frame {t}"
                if y_idx is not None and rep_parsed.motion[t][y_idx] < orig_parsed.motion[t][y_idx] - 1e-4:
                    return False, "GATE_7_ROOT_GROUND_DOWNWARD_PULL", f"Ground repair pulled root downward at frame {t}"
        elif finding.anomaly_type == AnomalyType.ROOT_DISCONTINUITY:
            jump_f = finding.peak_frame if finding.peak_frame is not None else finding.frame_start
            root_vel_limit = GATE7_ROOT_CONFIG["root_velocity_fraction_per_second"] * scale
            for t in range(jump_f + 2, min(fc, jump_f + 15)):
                for idx in (x_idx, y_idx, z_idx):
                    if idx is not None:
                        v_orig = (orig_parsed.motion[t][idx] - orig_parsed.motion[t - 1][idx]) / dt
                        v_rep = (rep_parsed.motion[t][idx] - rep_parsed.motion[t - 1][idx]) / dt
                        if abs(v_rep - v_orig) > root_vel_limit:
                            return False, "GATE_7_ROOT_JUMP_POST_VELOCITY_UNSTABLE", f"Root jump frame-to-frame velocity step {abs(v_rep - v_orig):.4f} exceeds limit {root_vel_limit:.4f} at frame {t}"
        elif finding.anomaly_type not in (AnomalyType.PLANTED_FOOT_SLIDING,):
            for t in range(fc):
                for idx in (x_idx, y_idx, z_idx):
                    if idx is not None and abs(rep_parsed.motion[t][idx] - orig_parsed.motion[t][idx]) > 1e-6:
                        return False, "GATE_7_UNAUTHORIZED_ROOT_TRANSLATION", f"Unrelated operator altered root translation channel {idx} at frame {t}"

        for prev_finding in previously_satisfied_findings:
            prev_ok, prev_err = evaluate_defect_improvement(orig_parsed, rep_parsed, prev_finding, floor_y)
            if not prev_ok:
                return False, "GATE_7_PREVIOUS_FINDING_REGRESSED", f"Previously repaired defect {prev_finding.finding_id} regressed: {prev_err}"

        return True, None, None

from typing import Dict, Tuple, List, Optional
from repair.contracts import WriteSetDeclaration

class WriteConflictError(ValueError):
    pass

INCOMPATIBLE_OPERATOR_PAIRS = {
    ("pose_pop_operator", "freeze_operator"),
    ("freeze_operator", "pose_pop_operator"),
    ("pose_pop_operator", "jitter_operator"),
    ("jitter_operator", "pose_pop_operator"),
}

class WriteSetTracker:
    @staticmethod
    def normalize_write_sets(write_sets: List[WriteSetDeclaration]) -> List[WriteSetDeclaration]:
        normalized = []
        for ws in write_sets:
            for frame in ws.target_frames:
                normalized.append(
                    WriteSetDeclaration(
                        operator_id=ws.operator_id,
                        target_frames=[frame],
                        joint_name=ws.joint_name,
                        channel_name=ws.channel_name,
                        channel_index=ws.channel_index,
                        max_permitted_change=ws.max_permitted_change,
                        blend_frames=ws.blend_frames,
                        derivation_reason=ws.derivation_reason,
                    )
                )
        return normalized

    @staticmethod
    def resolve_conflicts_and_merge(
        base_modifications: Dict[Tuple[int, int], float],
        candidate_modifications: Dict[Tuple[int, int], float],
        base_write_sets: List[WriteSetDeclaration],
        candidate_write_sets: List[WriteSetDeclaration],
        orig_values: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[Dict[Tuple[int, int], float], List[WriteSetDeclaration]]:
        norm_base = WriteSetTracker.normalize_write_sets(base_write_sets)
        norm_cand = WriteSetTracker.normalize_write_sets(candidate_write_sets)

        base_op_by_key = {}
        for ws in norm_base:
            base_op_by_key[(ws.target_frames[0], ws.channel_index)] = ws.operator_id

        cand_op_by_key = {}
        for ws in norm_cand:
            cand_op_by_key[(ws.target_frames[0], ws.channel_index)] = ws.operator_id

        merged_ws_dict: Dict[Tuple[int, int], WriteSetDeclaration] = {}
        for ws in norm_base + norm_cand:
            key = (ws.target_frames[0], ws.channel_index)
            if key in merged_ws_dict:
                existing = merged_ws_dict[key]
                merged_ws_dict[key] = WriteSetDeclaration(
                    operator_id=f"{existing.operator_id}+{ws.operator_id}",
                    target_frames=[key[0]],
                    joint_name=ws.joint_name,
                    channel_name=ws.channel_name,
                    channel_index=ws.channel_index,
                    max_permitted_change=min(existing.max_permitted_change, ws.max_permitted_change),
                    blend_frames=max(existing.blend_frames, ws.blend_frames),
                    derivation_reason=f"{existing.derivation_reason}; {ws.derivation_reason}",
                )
            else:
                merged_ws_dict[key] = ws

        merged_mods = dict(base_modifications)
        for key, cand_val in candidate_modifications.items():
            if key in merged_mods:
                base_op = base_op_by_key.get(key, "")
                cand_op = cand_op_by_key.get(key, "")
                if (base_op, cand_op) in INCOMPATIBLE_OPERATOR_PAIRS:
                    raise WriteConflictError(f"Incompatible operators {base_op} and {cand_op} at {key}")

                if orig_values and key in orig_values:
                    orig_val = orig_values[key]
                    max_bound = merged_ws_dict[key].max_permitted_change
                    if abs(cand_val - orig_val) > max_bound + 1e-4:
                        raise WriteConflictError(
                            f"Cumulative modification {abs(cand_val - orig_val)} exceeds merged bound {max_bound} at {key}"
                        )
                merged_mods[key] = cand_val
            else:
                merged_mods[key] = cand_val

        merged_write_sets = [merged_ws_dict[k] for k in sorted(merged_ws_dict)]
        return merged_mods, merged_write_sets

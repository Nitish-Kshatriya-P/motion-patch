import os
import uuid
import math
from typing import List, Set, Optional, Dict, Any, Tuple
from bvh_parser import parse_bvh_file, ParsedBVH
from models import AnomalyType, Finding
from repair.contracts import (
    RepairStatus,
    RepairResult,
    CandidateParameters,
    WriteSetDeclaration,
)
from repair.scoring import (
    SUPPORTED_DEFECT_OPERATORS,
    ROOT_JUMP_CANDIDATES,
    FREEZE_CANDIDATES,
    JITTER_CANDIDATES,
    GROUND_CANDIDATES,
)
from repair.token_patcher import TokenPatcher, TokenPatcherError
from repair.forward_kinematics import ForwardKinematicsEngine, KinematicsError
from repair.write_sets import WriteSetTracker, WriteConflictError
from repair.operators import RepairOperatorEngine
from repair.validation import ValidationPipeline

PRIORITY_ORDER = {
    AnomalyType.ROOT_DISCONTINUITY: 1,
    AnomalyType.OPTICAL_OCCLUSION_FLATLINE: 2,
    AnomalyType.EULER_GIMBAL_LOCK_FLIP: 3,
    AnomalyType.ROTATION_JITTER: 4,
    AnomalyType.TRANSLATION_JITTER: 4,
    AnomalyType.GROUND_PENETRATION: 5,
    AnomalyType.PLANTED_FOOT_SLIDING: 6,
}

class CanonicalRepairService:
    @staticmethod
    def execute_repair(
        input_bvh_path: str,
        output_dir: str,
        findings: List[Finding],
        approved_finding_ids: Set[str],
        original_asset_id: Optional[str] = None,
    ) -> RepairResult:
        if not os.path.exists(input_bvh_path):
            return RepairResult(
                status=RepairStatus.ERROR,
                reason_code="INPUT_FILE_NOT_FOUND",
                original_asset_id=original_asset_id,
            )

        with open(input_bvh_path, "rb") as f:
            raw_bytes = f.read()

        try:
            orig_parsed = parse_bvh_file(input_bvh_path)
            ForwardKinematicsEngine.validate_up_axis(orig_parsed)
        except Exception as e:
            return RepairResult(
                status=RepairStatus.ERROR,
                reason_code="ORIGINAL_BVH_INVALID",
                original_asset_id=original_asset_id,
                diagnostics={"error": str(e)},
            )

        fc = orig_parsed.metadata.frame_count
        tc = orig_parsed.metadata.total_channels

        try:
            first_data_offset, token_spans = TokenPatcher.validate_motion_structure(raw_bytes, fc, tc)
        except TokenPatcherError as tpe:
            return RepairResult(
                status=RepairStatus.ERROR,
                reason_code="MOTION_HEADER_INVALID",
                original_asset_id=original_asset_id,
                diagnostics={"error": str(tpe)},
            )

        token_lookup = {(f, ch): float(tok) for f, ch, s, e, tok in token_spans}

        orig_world_pos = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(orig_parsed, orig_parsed.motion)
        try:
            floor_y = ForwardKinematicsEngine.derive_ground_floor(orig_parsed, orig_world_pos)
        except KinematicsError:
            contact_joints = [j for j in orig_world_pos.keys() if any(k in j.lower() for k in ("foot", "toe", "ankle", "heel"))]
            if contact_joints:
                floor_y = min(min(orig_world_pos[j][t][1] for t in range(fc)) for j in contact_joints)
            else:
                floor_y = 0.0

        actionable = [
            f for f in findings
            if f.finding_id in approved_finding_ids and f.anomaly_type in SUPPORTED_DEFECT_OPERATORS
        ]
        if not actionable:
            return RepairResult(
                status=RepairStatus.REJECTED,
                reason_code="NO_ACTIONABLE_FINDINGS",
                original_asset_id=original_asset_id,
            )

        actionable.sort(key=lambda x: (PRIORITY_ORDER.get(x.anomaly_type, 99), x.frame_start, x.finding_id))

        working_motion = [list(row) for row in orig_parsed.motion]
        accumulated_modifications: Dict[Tuple[int, int], float] = {}
        accumulated_write_sets: List[WriteSetDeclaration] = []
        satisfied_findings: List[Finding] = []
        applied_operator_ids: List[str] = []
        diagnostics: Dict[str, Any] = {}
        latest_staging_path: Optional[str] = None
        last_failure_reason: Optional[str] = None

        for finding in actionable:
            candidates = CanonicalRepairService._get_candidate_parameter_grid(finding)
            candidate_passed = False

            for c_params in candidates:
                staging_candidate_path = None
                try:
                    cand_mods, cand_ws = RepairOperatorEngine.generate_candidate(
                        orig_parsed,
                        working_motion,
                        finding,
                        floor_y,
                        c_params,
                    )
                    if not cand_mods:
                        continue

                    merged_mods, merged_ws = WriteSetTracker.resolve_conflicts_and_merge(
                        accumulated_modifications,
                        cand_mods,
                        accumulated_write_sets,
                        cand_ws,
                        token_lookup,
                    )

                    valid_mods = TokenPatcher.validate_modifications_before_patching(
                        merged_mods,
                        token_spans,
                        merged_ws,
                        fc,
                        tc,
                    )

                    staging_candidate_path = os.path.join(output_dir, f"staging_{uuid.uuid4()}.bvh.tmp")
                    _, replacements = TokenPatcher.apply_patch_and_generate_ledger(
                        raw_bytes,
                        token_spans,
                        valid_mods,
                        staging_candidate_path,
                    )

                    passed, reason_code, err_msg = ValidationPipeline.run_production_gates(
                        input_bvh_path,
                        staging_candidate_path,
                        orig_parsed,
                        replacements,
                        valid_mods,
                        merged_ws,
                        finding,
                        satisfied_findings,
                        floor_y,
                    )

                    if passed:
                        if latest_staging_path and os.path.exists(latest_staging_path):
                            try:
                                os.remove(latest_staging_path)
                            except OSError:
                                pass
                        latest_staging_path = staging_candidate_path
                        accumulated_modifications = valid_mods
                        accumulated_write_sets = merged_ws
                        for (f_idx, ch_idx), new_val in valid_mods.items():
                            working_motion[f_idx][ch_idx] = new_val
                        satisfied_findings.append(finding)
                        applied_operator_ids.append(c_params.candidate_id)
                        candidate_passed = True
                        break
                    else:
                        last_failure_reason = reason_code
                        diagnostics[f"{finding.finding_id}_{c_params.candidate_id}"] = {
                            "gate_failure": reason_code,
                            "error": err_msg,
                        }
                        if staging_candidate_path and os.path.exists(staging_candidate_path):
                            try:
                                os.remove(staging_candidate_path)
                            except OSError:
                                pass
                except (TokenPatcherError, WriteConflictError, Exception) as exc:
                    last_failure_reason = getattr(exc, "args", ["OPERATOR_EXCEPTION"])[0]
                    diagnostics[f"{finding.finding_id}_{c_params.candidate_id}"] = {"exception": str(exc)}
                    if staging_candidate_path and os.path.exists(staging_candidate_path):
                        try:
                            os.remove(staging_candidate_path)
                        except OSError:
                            pass

        if not satisfied_findings or not latest_staging_path:
            if latest_staging_path and os.path.exists(latest_staging_path):
                try:
                    os.remove(latest_staging_path)
                except OSError:
                    pass
            return RepairResult(
                status=RepairStatus.REJECTED,
                reason_code=last_failure_reason or "ALL_CANDIDATES_REJECTED",
                original_asset_id=original_asset_id,
                diagnostics=diagnostics,
            )

        metrics = {
            "repaired_findings_count": len(satisfied_findings),
            "total_tokens_modified": len(accumulated_modifications),
            "floor_elevation": floor_y,
            "applied_operators": applied_operator_ids,
        }

        return RepairResult(
            status=RepairStatus.PASSED,
            staging_path=latest_staging_path,
            original_asset_id=original_asset_id,
            metrics=metrics,
            diagnostics=diagnostics,
            applied_operator_ids=applied_operator_ids,
            declared_write_sets=accumulated_write_sets,
        )

    @staticmethod
    def _get_candidate_parameter_grid(finding: Finding) -> List[CandidateParameters]:
        res = []
        if finding.anomaly_type == AnomalyType.ROOT_DISCONTINUITY:
            for idx, c in enumerate(ROOT_JUMP_CANDIDATES):
                res.append(CandidateParameters(candidate_id=c["id"], priority_index=idx, blend_frames=c["blend_frames"]))
        elif finding.anomaly_type == AnomalyType.OPTICAL_OCCLUSION_FLATLINE:
            for idx, c in enumerate(FREEZE_CANDIDATES):
                res.append(CandidateParameters(candidate_id=c["id"], priority_index=idx, method=c["method"], blend_frames=c["lead_frames"]))
        elif finding.anomaly_type == AnomalyType.EULER_GIMBAL_LOCK_FLIP:
            res.append(CandidateParameters(candidate_id="gimbal_slerp_unwrap", priority_index=0, blend_frames=1))
        elif finding.anomaly_type in (AnomalyType.ROTATION_JITTER, AnomalyType.TRANSLATION_JITTER):
            for idx, c in enumerate(JITTER_CANDIDATES):
                res.append(CandidateParameters(candidate_id=c["id"], priority_index=idx, cutoff_freq=c["cutoff_freq"], smoothing_window=3))
        elif finding.anomaly_type == AnomalyType.GROUND_PENETRATION:
            for idx, c in enumerate(GROUND_CANDIDATES):
                res.append(CandidateParameters(candidate_id=c["id"], priority_index=idx, smoothing_window=c["smoothing_window"]))
        else:
            res.append(CandidateParameters(candidate_id="default_op", priority_index=0))
        return res

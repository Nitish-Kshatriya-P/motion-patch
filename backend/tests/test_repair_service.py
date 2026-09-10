import os
import tempfile
import pytest
from bvh_parser import parse_bvh_file
from detector import build_shared_motion_representation
from models import AnomalyType, Finding, Severity, BodyPart
from repair.contracts import (
    RepairStatus,
    WriteSetDeclaration,
    CandidateParameters,
)
from repair.token_patcher import TokenPatcher, TokenPatcherError
from repair.forward_kinematics import ForwardKinematicsEngine
from repair.write_sets import WriteSetTracker, WriteConflictError
from repair.service import CanonicalRepairService

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "clean_cmu_reference.bvh")

def test_fk_engine_matches_detector_kinematics():
    parsed = parse_bvh_file(FIXTURE_PATH)
    smr = build_shared_motion_representation(parsed)
    fk_positions = ForwardKinematicsEngine.compute_joint_world_positions_for_motion(parsed, parsed.motion)

    for joint_name in smr.all_joint_names:
        assert joint_name in fk_positions
        smr_pos = smr.world_positions[joint_name]
        fk_pos = fk_positions[joint_name]
        assert len(smr_pos) == len(fk_pos)
        for t in range(min(len(smr_pos), 20)):
            for axis in range(3):
                assert abs(smr_pos[t][axis] - fk_pos[t][axis]) < 1e-3

def test_token_patcher_exact_headers_and_scientific_notation():
    raw_header = b"""HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  End Site
  {
    OFFSET 0.0 10.0 0.0
  }
}
MOTION
Frames: 2
Frame Time: 1.666667e-02
0.0 10.0 0.0 0.0 0.0 0.0
0.0 10.5 0.0 0.0 0.0 0.0
"""
    first_offset, spans = TokenPatcher.validate_motion_structure(raw_header, 2, 6)
    assert len(spans) == 12

    bad_frames = raw_header.replace(b"Frames: 2", b"Frames: 2 extra")
    with pytest.raises(TokenPatcherError):
        TokenPatcher.validate_motion_structure(bad_frames, 2, 6)

    bad_time = raw_header.replace(b"Frame Time: 1.666667e-02", b"Frame Time: NaN")
    with pytest.raises(TokenPatcherError):
        TokenPatcher.validate_motion_structure(bad_time, 2, 6)

    nan_tok = raw_header.replace(b"10.5", b"NaN")
    with pytest.raises(TokenPatcherError):
        TokenPatcher.validate_motion_structure(nan_tok, 2, 6)

def test_token_patcher_zero_modification_calculated():
    parsed = parse_bvh_file(FIXTURE_PATH)
    with open(FIXTURE_PATH, "rb") as f:
        raw_bytes = f.read()
    fc = parsed.metadata.frame_count
    tc = parsed.metadata.total_channels
    _, spans = TokenPatcher.validate_motion_structure(raw_bytes, fc, tc)

    ws = [
        WriteSetDeclaration(
            operator_id="test_op",
            target_frames=[5],
            joint_name="Hips",
            channel_name="Yposition",
            channel_index=1,
            max_permitted_change=1.0,
            blend_frames=1,
            derivation_reason="test",
        )
    ]

    with pytest.raises(TokenPatcherError, match="ZERO_MODIFICATION_CALCULATED"):
        TokenPatcher.validate_modifications_before_patching({}, spans, ws, fc, tc)

    orig_val = float(spans[5 * tc + 1][4])
    with pytest.raises(TokenPatcherError, match="ZERO_MODIFICATION_CALCULATED"):
        TokenPatcher.validate_modifications_before_patching({(5, 1): orig_val}, spans, ws, fc, tc)

def test_write_set_tracker_normalization_and_conflict_resolution():
    ws1 = WriteSetDeclaration(
        operator_id="op1",
        target_frames=[1, 2],
        joint_name="Hips",
        channel_name="Yposition",
        channel_index=1,
        max_permitted_change=5.0,
        blend_frames=2,
        derivation_reason="op1",
    )
    ws2 = WriteSetDeclaration(
        operator_id="op2",
        target_frames=[2, 3],
        joint_name="Hips",
        channel_name="Yposition",
        channel_index=1,
        max_permitted_change=3.0,
        blend_frames=1,
        derivation_reason="op2",
    )

    base_mods = {(1, 1): 10.0, (2, 1): 11.0}
    cand_mods = {(2, 1): 11.5, (3, 1): 12.0}

    merged_mods, merged_ws = WriteSetTracker.resolve_conflicts_and_merge(
        base_mods,
        cand_mods,
        [ws1],
        [ws2],
    )

    assert (2, 1) in merged_mods
    assert merged_mods[(2, 1)] == 11.5
    keys = [(w.target_frames[0], w.channel_index) for w in merged_ws]
    assert keys == sorted(keys)

    bad_ws_pop = WriteSetDeclaration(
        operator_id="pose_pop_operator",
        target_frames=[5],
        joint_name="Arm",
        channel_name="Xrotation",
        channel_index=4,
        max_permitted_change=180.0,
        blend_frames=1,
        derivation_reason="pop",
    )
    bad_ws_frz = WriteSetDeclaration(
        operator_id="freeze_operator",
        target_frames=[5],
        joint_name="Arm",
        channel_name="Xrotation",
        channel_index=4,
        max_permitted_change=180.0,
        blend_frames=1,
        derivation_reason="freeze",
    )

    with pytest.raises(WriteConflictError):
        WriteSetTracker.resolve_conflicts_and_merge(
            {(5, 4): 45.0},
            {(5, 4): 90.0},
            [bad_ws_pop],
            [bad_ws_frz],
        )

def test_canonical_repair_service_end_to_end_root_jump():
    with tempfile.TemporaryDirectory() as tmp_dir:
        parsed = parse_bvh_file(FIXTURE_PATH)
        modified_motion = [list(r) for r in parsed.motion]
        fc = len(modified_motion)
        jump_frame = 10
        offset = 5.0
        for t in range(jump_frame, fc):
            modified_motion[t][0] += offset

        defect_file = os.path.join(tmp_dir, "defect_root_jump.bvh")
        with open(FIXTURE_PATH, "r") as f_orig, open(defect_file, "w") as f_out:
            for line in f_orig:
                f_out.write(line)
                if line.strip() == "Frame Time: 0.033333" or "Frame Time:" in line:
                    break
            for row in modified_motion:
                f_out.write(" ".join(f"{v:.6f}" for v in row) + "\n")

        finding = Finding(
            finding_id="find_root_jump_1",
            analysis_id="an_1",
            affected_joint=parsed.root_node.name,
            affected_body_part=BodyPart.PELVIS,
            frame_start=jump_frame,
            frame_end=jump_frame + 2,
            peak_frame=jump_frame,
            time_start=jump_frame * parsed.metadata.frame_time,
            time_end=(jump_frame + 2) * parsed.metadata.frame_time,
            anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
            severity=Severity.HIGH,
            confidence=0.95,
            explanation="Synthesized root jump defect",
        )

        res = CanonicalRepairService.execute_repair(
            input_bvh_path=defect_file,
            output_dir=tmp_dir,
            findings=[finding],
            approved_finding_ids={"find_root_jump_1"},
            original_asset_id="asset_orig_1",
        )

        assert res.status == RepairStatus.PASSED
        assert res.staging_path is not None
        assert os.path.exists(res.staging_path)

        rep_parsed = parse_bvh_file(res.staging_path)
        assert rep_parsed.metadata.frame_count == parsed.metadata.frame_count
        assert rep_parsed.metadata.total_channels == parsed.metadata.total_channels
        assert rep_parsed.metadata.skeleton_signature == parsed.metadata.skeleton_signature

        if os.path.exists(res.staging_path):
            os.remove(res.staging_path)

def test_canonical_repair_service_rejection_cleans_staging_files():
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = CanonicalRepairService.execute_repair(
            input_bvh_path=FIXTURE_PATH,
            output_dir=tmp_dir,
            findings=[],
            approved_finding_ids=set(),
            original_asset_id="orig_asset",
        )

        assert res.status == RepairStatus.REJECTED
        assert res.staging_path is None
        tmp_files = [f for f in os.listdir(tmp_dir) if f.endswith(".tmp")]
        assert len(tmp_files) == 0

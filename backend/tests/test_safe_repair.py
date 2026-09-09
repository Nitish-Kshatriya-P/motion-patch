import os
os.environ["TESTING"] = "1"
import tempfile
import hashlib
import json
import uuid
import shutil
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from main import app
from config import UPLOAD_DIR, BLENDER_BOILERPLATE
from database import (
    init_db,
    get_db,
    insert_asset,
    insert_analysis,
    insert_workflow_session,
    insert_repair_plan,
    approve_plan_transaction,
    get_asset,
    get_workflow_session,
)
from models import (
    Asset,
    Analysis,
    Finding,
    WorkflowSession,
    RepairPlan,
    Approval,
    LifecycleState,
    AnalysisStatus,
    AnomalyType,
    Severity,
    BodyPart,
    BVHMetadata,
    AgentSpecification,
    BatchFile,
    Status,
    compute_roster_hash,
)
from bvh_parser import parse_bvh_file
from detector import build_shared_motion_representation
from agent import (
    apply_direct_bvh_channel_patch,
    build_edit_mask,
    validate_strict_edit_mask,
    check_repair_invariants,
    validate_pop_repair,
    validate_jitter_repair,
    validate_foot_slide_repair,
    validate_freeze_repair,
    validate_root_jump_repair,
    validate_pose_violation_repair,
    validate_repair_quality,
    compute_deterministic_repairs,
    execute_deterministic_safe_repair,
)
from batch_orchestrator import process_batch_file

MULTI_JOINT_BVH = """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT RightArm
  {
    OFFSET 5.0 10.0 0.0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT RightForeArm
    {
      OFFSET 0.0 -5.0 0.0
      CHANNELS 3 Zrotation Xrotation Yrotation
      End Site
      {
        OFFSET 0.0 -5.0 0.0
      }
    }
  }
  JOINT LeftLeg
  {
    OFFSET -2.0 -5.0 0.0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT LeftFoot
    {
      OFFSET 0.0 -5.0 0.0
      CHANNELS 3 Zrotation Xrotation Yrotation
      End Site
      {
        OFFSET 0.0 -1.0 1.0
      }
    }
  }
}
MOTION
Frames: 6
Frame Time: 0.033333
0.0 10.0 0.0 0.0 0.0 0.0 10.0 20.0 5.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 10.0 0.0 0.0 0.0 0.0 12.0 21.0 5.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 10.0 0.0 0.0 0.0 0.0 65.0 75.0 30.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 10.0 0.0 0.0 0.0 0.0 14.0 22.0 5.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 10.0 0.0 0.0 0.0 0.0 15.0 23.0 5.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 10.0 0.0 0.0 0.0 0.0 16.0 24.0 5.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
"""

@pytest.fixture
def bvh_environment():
    temp_dir = tempfile.mkdtemp()
    orig_path = os.path.join(temp_dir, "original.bvh")
    with open(orig_path, "w", encoding="utf-8") as f:
        f.write(MULTI_JOINT_BVH)

    yield temp_dir, orig_path
    shutil.rmtree(temp_dir, ignore_errors=True)

def test_separate_asset_output_never_mutates_inplace(bvh_environment):
    temp_dir, orig_path = bvh_environment
    with open(orig_path, "rb") as f:
        orig_hash_before = hashlib.sha256(f.read()).hexdigest()

    with pytest.raises(ValueError) as excinfo:
        apply_direct_bvh_channel_patch(
            original_bvh_path=orig_path,
            output_bvh_path=orig_path,
            channel_modifications={(0, 0): 10.0},
            authorized_edit_mask={(0, 0)},
        )
    assert "never mutate in-place" in str(excinfo.value)

    out_path = os.path.join(temp_dir, "patched.bvh")
    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=out_path,
        channel_modifications={(2, 6): 13.0},
        authorized_edit_mask={(2, 6)},
    )
    assert os.path.exists(out_path)
    assert out_path != orig_path

    with open(orig_path, "rb") as f:
        orig_hash_after = hashlib.sha256(f.read()).hexdigest()
    assert orig_hash_before == orig_hash_after

def test_direct_bvh_token_patching_zero_float_drift(bvh_environment):
    temp_dir, orig_path = bvh_environment
    out_path = os.path.join(temp_dir, "patched_zero_drift.bvh")

    parsed = parse_bvh_file(orig_path)
    authorized = {(2, 6), (2, 7)}
    patches = {(2, 6): 13.5, (2, 7): 21.5}

    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=out_path,
        channel_modifications=patches,
        authorized_edit_mask=authorized,
    )

    with open(orig_path, "r", encoding="utf-8") as f:
        orig_lines = [l.strip() for l in f if l.strip()]
    with open(out_path, "r", encoding="utf-8") as f:
        rep_lines = [l.strip() for l in f if l.strip()]

    orig_motion_idx = orig_lines.index("MOTION")
    rep_motion_idx = rep_lines.index("MOTION")
    assert orig_lines[:orig_motion_idx + 3] == rep_lines[:rep_motion_idx + 3]

    orig_frames = orig_lines[orig_motion_idx + 3:]
    rep_frames = rep_lines[rep_motion_idx + 3:]
    assert len(orig_frames) == len(rep_frames)

    for f_idx, (o_line, r_line) in enumerate(zip(orig_frames, rep_frames)):
        o_toks = o_line.split()
        r_toks = r_line.split()
        for ch_idx, (o_tok, r_tok) in enumerate(zip(o_toks, r_toks)):
            if (f_idx, ch_idx) in patches:
                assert r_tok == f"{patches[(f_idx, ch_idx)]:.6f}"
            else:
                assert r_tok == o_tok

def test_strict_edit_mask_protection(bvh_environment):
    temp_dir, orig_path = bvh_environment
    parsed = parse_bvh_file(orig_path)

    spec = AgentSpecification(
        agent_id="agent-arm",
        role="RightArm Kinematics Specialist",
        target_bones=["RightArm"],
        target_frames=[1, 3],
    )
    authorized_mask = build_edit_mask(parsed, roster=[spec])

    arm_channels = set(parsed.joint_map["RightArm"].channel_indices)
    for t in range(1, 4):
        for ch in arm_channels:
            assert (t, ch) in authorized_mask

    forearm_channels = set(parsed.joint_map["RightForeArm"].channel_indices)
    for t in range(6):
        for ch in forearm_channels:
            assert (t, ch) not in authorized_mask

    unauthorized_out = os.path.join(temp_dir, "unauthorized.bvh")
    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=unauthorized_out,
        channel_modifications={(2, list(forearm_channels)[0]): 45.0},
        authorized_edit_mask={(2, list(forearm_channels)[0])},
    )
    rep_parsed = parse_bvh_file(unauthorized_out)
    is_valid, violations = validate_strict_edit_mask(parsed, rep_parsed, authorized_mask)
    assert is_valid is False
    assert any("Strict edit mask violation" in v for v in violations)

    authorized_out = os.path.join(temp_dir, "authorized_parent_rot.bvh")
    arm_ch = parsed.joint_map["RightArm"].channel_indices[0]
    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=authorized_out,
        channel_modifications={(2, arm_ch): 0.0},
        authorized_edit_mask=authorized_mask,
    )
    auth_rep_parsed = parse_bvh_file(authorized_out)
    auth_valid, auth_violations = validate_strict_edit_mask(parsed, auth_rep_parsed, authorized_mask)
    assert auth_valid is True
    assert len(auth_violations) == 0

    orig_rep = build_shared_motion_representation(parsed)
    auth_rep = build_shared_motion_representation(auth_rep_parsed)
    orig_forearm_pos = orig_rep.world_positions["RightForeArm"][2]
    rep_forearm_pos = auth_rep.world_positions["RightForeArm"][2]
    assert orig_forearm_pos != rep_forearm_pos

def test_invariant_checks_rejections(bvh_environment):
    temp_dir, orig_path = bvh_environment
    parsed = parse_bvh_file(orig_path)
    orig_rep = build_shared_motion_representation(parsed)

    valid_same, violations = check_repair_invariants(parsed, parsed, orig_rep=orig_rep, rep_rep=orig_rep)
    assert valid_same is True
    assert len(violations) == 0

    penetration_out = os.path.join(temp_dir, "penetration.bvh")
    hips_y_ch = parsed.joint_map["Hips"].channel_indices[1]
    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=penetration_out,
        channel_modifications={(t, hips_y_ch): -20.0 for t in range(6)},
        authorized_edit_mask={(t, hips_y_ch) for t in range(6)},
    )
    pen_parsed = parse_bvh_file(penetration_out)
    pen_rep = build_shared_motion_representation(pen_parsed)
    pen_valid, pen_violations = check_repair_invariants(parsed, pen_parsed, orig_rep=orig_rep, rep_rep=pen_rep)
    assert pen_valid is False
    assert any("Ground penetration invariant violated" in v for v in pen_violations)

def test_pop_validation_rejects_harmful_and_ineffective(bvh_environment):
    temp_dir, orig_path = bvh_environment
    parsed = parse_bvh_file(orig_path)
    orig_rep = build_shared_motion_representation(parsed)

    ineffective_out = os.path.join(temp_dir, "ineffective_pop.bvh")
    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=ineffective_out,
        channel_modifications={},
        authorized_edit_mask=set(),
    )
    ineff_parsed = parse_bvh_file(ineffective_out)
    ineff_rep = build_shared_motion_representation(ineff_parsed)
    ok_ineff, err_ineff = validate_pop_repair(
        parsed, ineff_parsed, orig_rep, ineff_rep, "RightArm", 2, 2
    )
    assert ok_ineff is False
    assert "was not reduced" in err_ineff

    valid_out = os.path.join(temp_dir, "valid_pop.bvh")
    arm_indices = parsed.joint_map["RightArm"].channel_indices
    arm_patches = {
        (2, arm_indices[0]): 13.0,
        (2, arm_indices[1]): 21.5,
        (2, arm_indices[2]): 5.0,
    }
    apply_direct_bvh_channel_patch(
        original_bvh_path=orig_path,
        output_bvh_path=valid_out,
        channel_modifications=arm_patches,
        authorized_edit_mask=set(arm_patches.keys()),
    )
    val_parsed = parse_bvh_file(valid_out)
    val_rep = build_shared_motion_representation(val_parsed)
    ok_val, err_val = validate_pop_repair(
        parsed, val_parsed, orig_rep, val_rep, "RightArm", 2, 2
    )
    assert ok_val is True
    assert err_val == ""

def test_jitter_validation_rejects_oversmoothing(bvh_environment):
    temp_dir, _ = bvh_environment
    jitter_bvh_content = """HIERARCHY
ROOT Spine
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 3 Zrotation Xrotation Yrotation
  End Site
  {
    OFFSET 0.0 5.0 0.0
  }
}
MOTION
Frames: 8
Frame Time: 0.033333
0.0 10.0 0.0
0.0 18.0 0.0
0.0 8.0 0.0
0.0 19.0 0.0
0.0 7.0 0.0
0.0 18.0 0.0
0.0 9.0 0.0
0.0 10.0 0.0
"""
    jitter_path = os.path.join(temp_dir, "jitter.bvh")
    with open(jitter_path, "w", encoding="utf-8") as f:
        f.write(jitter_bvh_content)

    orig_parsed = parse_bvh_file(jitter_path)

    oversmoothed_out = os.path.join(temp_dir, "oversmoothed_jitter.bvh")
    flat_patches = {(t, 1): 0.0 for t in range(8)}
    apply_direct_bvh_channel_patch(
        original_bvh_path=jitter_path,
        output_bvh_path=oversmoothed_out,
        channel_modifications=flat_patches,
        authorized_edit_mask=set(flat_patches.keys()),
    )
    over_parsed = parse_bvh_file(oversmoothed_out)
    ok_over, err_over = validate_jitter_repair(orig_parsed, over_parsed, "Spine", 1, 6)
    assert ok_over is False
    assert "smoother is better" in err_over

    valid_smooth_out = os.path.join(temp_dir, "valid_smooth_jitter.bvh")
    smooth_patches = {
        (1, 1): 12.0,
        (2, 1): 13.0,
        (3, 1): 14.0,
        (4, 1): 13.0,
        (5, 1): 14.0,
        (6, 1): 12.0,
    }
    apply_direct_bvh_channel_patch(
        original_bvh_path=jitter_path,
        output_bvh_path=valid_smooth_out,
        channel_modifications=smooth_patches,
        authorized_edit_mask=set(smooth_patches.keys()),
    )
    smooth_parsed = parse_bvh_file(valid_smooth_out)
    ok_smooth, err_smooth = validate_jitter_repair(orig_parsed, smooth_parsed, "Spine", 1, 6)
    assert ok_smooth is True
    assert err_smooth == ""

def test_foot_slide_validation_rejects_new_penetration(bvh_environment):
    temp_dir, _ = bvh_environment
    foot_bvh_content = """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 10.0 0.0
  CHANNELS 3 Xposition Yposition Zposition
  JOINT LeftFoot
  {
    OFFSET 0.0 -10.0 0.0
    CHANNELS 3 Xposition Yposition Zposition
    End Site
    {
      OFFSET 0.0 0.0 2.0
    }
  }
}
MOTION
Frames: 5
Frame Time: 0.033333
0.0 10.0 0.0 0.0 0.0 0.0
0.0 10.0 0.0 2.0 0.0 1.0
0.0 10.0 0.0 4.0 0.0 2.0
0.0 10.0 0.0 6.0 0.0 3.0
0.0 10.0 0.0 8.0 0.0 4.0
"""
    foot_path = os.path.join(temp_dir, "foot_slide.bvh")
    with open(foot_path, "w", encoding="utf-8") as f:
        f.write(foot_bvh_content)

    orig_parsed = parse_bvh_file(foot_path)
    orig_rep = build_shared_motion_representation(orig_parsed)

    penetration_out = os.path.join(temp_dir, "foot_penetration.bvh")
    pen_patches = {
        (t, 3): 0.0 for t in range(5)
    }
    pen_patches.update({(t, 4): -5.0 for t in range(5)})
    pen_patches.update({(t, 5): 0.0 for t in range(5)})
    apply_direct_bvh_channel_patch(
        original_bvh_path=foot_path,
        output_bvh_path=penetration_out,
        channel_modifications=pen_patches,
        authorized_edit_mask=set(pen_patches.keys()),
    )
    pen_parsed = parse_bvh_file(penetration_out)
    pen_rep = build_shared_motion_representation(pen_parsed)
    ok_pen, err_pen = validate_foot_slide_repair(
        orig_parsed, pen_parsed, orig_rep, pen_rep, "LeftFoot", 0, 4
    )
    assert ok_pen is False
    assert "new ground penetration" in err_pen

    valid_foot_out = os.path.join(temp_dir, "foot_pinned.bvh")
    pinned_patches = {
        (t, 3): 0.0 for t in range(5)
    }
    pinned_patches.update({(t, 4): 0.0 for t in range(5)})
    pinned_patches.update({(t, 5): 0.0 for t in range(5)})
    apply_direct_bvh_channel_patch(
        original_bvh_path=foot_path,
        output_bvh_path=valid_foot_out,
        channel_modifications=pinned_patches,
        authorized_edit_mask=set(pinned_patches.keys()),
    )
    pinned_parsed = parse_bvh_file(valid_foot_out)
    pinned_rep = build_shared_motion_representation(pinned_parsed)
    ok_pin, err_pin = validate_foot_slide_repair(
        orig_parsed, pinned_parsed, orig_rep, pinned_rep, "LeftFoot", 0, 4
    )
    assert ok_pin is True
    assert err_pin == ""

def test_freeze_and_root_jump_validation(bvh_environment):
    temp_dir, _ = bvh_environment
    freeze_bvh = """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 3 Xposition Yposition Zposition
  End Site
  {
    OFFSET 0.0 1.0 0.0
  }
}
MOTION
Frames: 6
Frame Time: 0.033333
0.0 0.0 0.0
50.0 0.0 0.0
50.0 0.0 0.0
50.0 0.0 0.0
50.0 0.0 0.0
55.0 0.0 0.0
"""
    f_path = os.path.join(temp_dir, "freeze.bvh")
    with open(f_path, "w", encoding="utf-8") as f:
        f.write(freeze_bvh)

    f_parsed = parse_bvh_file(f_path)
    ok_fr, err_fr = validate_freeze_repair(f_parsed, f_parsed, "Hips", 1, 4)
    assert ok_fr is False
    assert "remains unnaturally frozen" in err_fr

    ok_jump, err_jump = validate_root_jump_repair(f_parsed, f_parsed, "Hips", 1, 1)
    assert ok_jump is False
    assert "jump discontinuity" in err_jump

def test_shared_quality_gate_single_file_route(bvh_environment):
    temp_dir, orig_path = bvh_environment
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    import database
    orig_db = database.DB_PATH
    database.DB_PATH = db_path

    asset_id = "asset-gate-test"
    bvh_upload_path = os.path.join(UPLOAD_DIR, f"{asset_id}.bvh")
    shutil.copyfile(orig_path, bvh_upload_path)

    parsed = parse_bvh_file(bvh_upload_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    asset = Asset(
        asset_id=asset_id,
        filename="test_gate.bvh",
        file_path=bvh_upload_path,
        file_size_bytes=os.path.getsize(bvh_upload_path),
        content_hash=parsed.raw_content_hash,
        skeleton_signature=parsed.metadata.skeleton_signature,
        metadata=parsed.metadata,
        created_at=now_iso,
    )
    session = WorkflowSession(
        session_id="session-gate-01",
        asset_id=asset_id,
        analysis_id="analysis-gate-01",
        lifecycle_state=LifecycleState.AWAITING_APPROVAL,
        created_at=now_iso,
        updated_at=now_iso,
    )
    agent_spec = AgentSpecification(
        agent_id="agent-gate-01",
        role="RightArm Kinematic Pop Specialist",
        target_bones=["RightArm"],
        target_frames=[2, 2],
    )
    plan = RepairPlan(
        plan_id="plan-gate-01",
        session_id="session-gate-01",
        analysis_id="analysis-gate-01",
        analysis_hash="analysis_hash_gate",
        version=1,
        selected_finding_ids=[],
        proposed_roster=[agent_spec],
        status="PENDING",
        created_at=now_iso,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    approval = Approval(
        approval_id="approval-gate-01",
        session_id="session-gate-01",
        plan_id="plan-gate-01",
        repair_plan_version=1,
        analysis_hash="analysis_hash_gate",
        selected_finding_ids=[],
        roster_hash=compute_roster_hash([agent_spec]),
        approved_by="test_user",
        approved_at=now_iso,
        valid_until=plan.expires_at,
    )
    analysis = Analysis(
        analysis_id="analysis-gate-01",
        asset_id=asset_id,
        content_hash=parsed.raw_content_hash,
        skeleton_signature=parsed.metadata.skeleton_signature,
        analysis_hash="analysis_hash_gate",
        status=AnalysisStatus.FINDINGS,
        findings=[
            Finding(
                finding_id="f-pop-01",
                analysis_id="analysis-gate-01",
                affected_joint="RightArm",
                affected_body_part=BodyPart.ARM,
                frame_start=2,
                frame_end=2,
                time_start=0.066,
                time_end=0.066,
                anomaly_type=AnomalyType.OPTICAL_MARKER_SWAP,
                severity=Severity.HIGH,
                confidence=0.9,
                evidence={},
                explanation="Pop on RightArm",
                created_at=now_iso,
            )
        ],
        created_at=now_iso,
    )

    with get_db(db_path) as conn:
        with conn:
            insert_asset(conn, asset)
            insert_analysis(conn, analysis)
            insert_workflow_session(conn, session)
            insert_repair_plan(conn, plan)
            approve_plan_transaction(conn, approval, now_iso)

    with TestClient(app) as client:
        req_runs = {
            "session_id": "session-gate-01",
            "plan_id": "plan-gate-01",
            "approval_id": "approval-gate-01",
        }
        res_runs = client.post("/runs", json=req_runs)
        assert res_runs.status_code == 200, res_runs.json()
        runs_data = res_runs.json()
        assert runs_data["status"] == "COMPLETED"
        repaired_asset_id = runs_data["asset_id"]
        assert repaired_asset_id != asset_id

        repaired_bvh_path = os.path.join(UPLOAD_DIR, f"{repaired_asset_id}.bvh")
        assert os.path.exists(repaired_bvh_path)
        assert os.path.abspath(repaired_bvh_path) != os.path.abspath(bvh_upload_path)

        with open(bvh_upload_path, "r", encoding="utf-8") as f:
            bvh_upload_content = f.read()
        assert "65.0 75.0 30.0" in bvh_upload_content

        with open(repaired_bvh_path, "r", encoding="utf-8") as f:
            repaired_content = f.read()
        assert "65.0 75.0 30.0" not in repaired_content

    database.DB_PATH = orig_db
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(bvh_upload_path):
        os.remove(bvh_upload_path)

def test_walkfwd_mocap_fixture_safe_repair(tmp_path):
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "01_WalkFwd_Loop_RightContactDropout.bvh")
    if not os.path.exists(fixture_path):
        pytest.skip("Fixture 01_WalkFwd_Loop_RightContactDropout.bvh not found")

    parsed = parse_bvh_file(fixture_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    findings = [
        Finding(
            finding_id="f1",
            affected_joint="RightFoot",
            affected_body_part="foot",
            frame_start=21,
            frame_end=28,
            time_start=0.35,
            time_end=0.46,
            anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
            severity=Severity.HIGH,
            confidence=0.95,
            evidence={"frames": [21, 28]},
            explanation="Foot contact dropout and ground sliding",
            created_at=now_iso,
        ),
        Finding(
            finding_id="f2",
            affected_joint="LeftLeg",
            affected_body_part="leg",
            frame_start=21,
            frame_end=28,
            time_start=0.35,
            time_end=0.46,
            anomaly_type=AnomalyType.EULER_GIMBAL_LOCK_FLIP,
            severity=Severity.MEDIUM,
            confidence=0.9,
            evidence={"frames": [21, 28]},
            explanation="Gimbal flip on LeftLeg",
            created_at=now_iso,
        ),
    ]

    from models import AgentSpecification
    roster = [
        AgentSpecification(
            agent_id="a1",
            role="Left Lower Limb Stabilization and Contact Specialist",
            target_bones=["LeftLeg", "LeftFoot"],
            target_frames=[16, 40],
            system_instruction="Fix LeftLeg and LeftFoot sliding and flips",
            tools=["euler_unroll_filter", "gaussian_smoother"],
        ),
        AgentSpecification(
            agent_id="a2",
            role="Right Lower Body Occlusion Specialist",
            target_bones=["RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"],
            target_frames=[21, 46],
            system_instruction="Fix Right leg chain",
            tools=["kinematic_interpolator"],
        ),
    ]

    out_file = str(tmp_path / "repaired_walk.bvh")
    rep_path, metrics = execute_deterministic_safe_repair(
        input_bvh_path=fixture_path,
        output_bvh_path=out_file,
        roster=roster,
        findings=findings,
    )
    assert os.path.exists(rep_path)
    assert metrics["qa_passed"] is True
    assert metrics["patches_applied"] > 0

    repaired_parsed = parse_bvh_file(rep_path)
    assert repaired_parsed.metadata.frame_count == parsed.metadata.frame_count
    assert abs(repaired_parsed.metadata.frame_time - parsed.metadata.frame_time) < 1e-5
    assert repaired_parsed.metadata.total_channels == parsed.metadata.total_channels
    assert repaired_parsed.metadata.skeleton_signature == parsed.metadata.skeleton_signature

def test_blender_boilerplate_export_invariants():
    from config import BLENDER_BOILERPLATE
    assert "root_transform_only=True" in BLENDER_BOILERPLATE
    assert "frame_start=bpy.context.scene.frame_start" in BLENDER_BOILERPLATE
    assert "frame_end=bpy.context.scene.frame_end" in BLENDER_BOILERPLATE

def test_blender_invariant_guard_rejects_corrupted_export(tmp_path):
    from blender import execute_blender_script
    from models import ExecutionParams

    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "01_WalkFwd_Loop_RightContactDropout.bvh")
    if not os.path.exists(fixture_path):
        pytest.skip("Fixture not found")

    upload_dir = str(tmp_path)
    temp_id = "test_corrupt_export"
    params = ExecutionParams(
        input_bvh_path=fixture_path,
        script_code="import bpy\n",
        upload_dir=upload_dir,
        temp_output_id=temp_id,
    )
    res_path = execute_blender_script(params)
    assert os.path.exists(res_path)
    res_parsed = parse_bvh_file(res_path)
    orig_parsed = parse_bvh_file(fixture_path)
    assert res_parsed.metadata.frame_count == orig_parsed.metadata.frame_count
    assert res_parsed.metadata.total_channels == orig_parsed.metadata.total_channels
    assert res_parsed.metadata.skeleton_signature == orig_parsed.metadata.skeleton_signature

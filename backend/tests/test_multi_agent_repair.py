import os
os.environ["TESTING"] = "1"
import ast
import tempfile
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
    RunExecutionRequest,
    LegacyRunBlenderRequest,
    BatchFile,
    Status,
    compute_roster_hash,
)
from agent import (
    generate_worker_code,
    aggregate_worker_scripts,
    validate_qa_script,
    generate_multi_agent_script,
)
from batch_orchestrator import process_batch_file

SAMPLE_BVH = """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT LeftLeg
  {
    OFFSET 2.0 -5.0 0.0
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
Frames: 2
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
"""

@pytest.fixture
def test_setup():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    import database
    orig_path = database.DB_PATH
    database.DB_PATH = db_path

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    asset_id = str(uuid.uuid4())
    bvh_file = os.path.join(UPLOAD_DIR, f"{asset_id}.bvh")
    with open(bvh_file, "w", encoding="utf-8") as f:
        f.write(SAMPLE_BVH)

    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_multi_repair",
        root_name="Hips",
        joints=["Hips", "LeftLeg", "LeftFoot"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition", "Zrotation", "Xrotation", "Yrotation"]},
        total_channels=12,
        frame_count=2,
        frame_time=0.033333,
        duration_seconds=0.066666,
        skeleton_scale=10.0,
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    asset = Asset(
        asset_id=asset_id,
        filename="test_motion.bvh",
        file_path=bvh_file,
        file_size_bytes=len(SAMPLE_BVH),
        content_hash="hash_multi_1",
        skeleton_signature="sig_multi_repair",
        metadata=meta,
        created_at=now_iso,
    )

    finding = Finding(
        finding_id="finding-foot-01",
        analysis_id="analysis-multi-01",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=0,
        frame_end=2,
        time_start=0.0,
        time_end=0.066,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.95,
        evidence={"slide_distance": 4.2},
        explanation="Planted foot sliding",
        created_at=now_iso,
    )
    analysis = Analysis(
        analysis_id="analysis-multi-01",
        asset_id=asset_id,
        content_hash="hash_multi_1",
        skeleton_signature="sig_multi_repair",
        analysis_hash="analysis_hash_multi_1",
        status=AnalysisStatus.FINDINGS,
        findings=[finding],
        created_at=now_iso,
    )
    session = WorkflowSession(
        session_id="session-multi-01",
        asset_id=asset_id,
        analysis_id="analysis-multi-01",
        lifecycle_state=LifecycleState.AWAITING_APPROVAL,
        created_at=now_iso,
        updated_at=now_iso,
    )

    agent_spec = AgentSpecification(
        agent_id="agent-foot-01",
        role="LeftFoot Ground Contact & Anti-Slide Specialist",
        assigned_joints=["LeftFoot"],
        target_bones=["LeftFoot"],
        target_frames=[0, 2],
        tools=["query_clickhouse_rag"],
        status="SPAWNED",
    )
    plan = RepairPlan(
        plan_id="plan-multi-01",
        session_id="session-multi-01",
        analysis_id="analysis-multi-01",
        analysis_hash="analysis_hash_multi_1",
        version=1,
        selected_finding_ids=["finding-foot-01"],
        proposed_roster=[agent_spec],
        status="PENDING",
        created_at=now_iso,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    approval = Approval(
        approval_id="approval-multi-01",
        session_id="session-multi-01",
        plan_id="plan-multi-01",
        repair_plan_version=1,
        analysis_hash="analysis_hash_multi_1",
        selected_finding_ids=["finding-foot-01"],
        roster_hash=compute_roster_hash([agent_spec]),
        approved_by="authenticated_user",
        approved_at=now_iso,
        valid_until=plan.expires_at,
    )

    with get_db(db_path) as conn:
        with conn:
            insert_asset(conn, asset)
            insert_analysis(conn, analysis)
            insert_workflow_session(conn, session)
            insert_repair_plan(conn, plan)
            approve_plan_transaction(conn, approval, now_iso)

    with TestClient(app) as client:
        yield client, db_path, asset_id, bvh_file

    database.DB_PATH = orig_path
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(bvh_file):
        os.remove(bvh_file)

def test_aggregator_combines_worker_codes():
    spec1 = AgentSpecification(
        agent_id="spec-1",
        role="LeftFoot Ground Contact Specialist",
        target_bones=["LeftFoot"],
        target_frames=[0, 50],
    )
    spec2 = AgentSpecification(
        agent_id="spec-2",
        role="Spine Kinematic Jitter Smoother",
        target_bones=["Spine"],
        target_frames=[20, 80],
    )
    code1 = generate_worker_code(spec1)
    code2 = generate_worker_code(spec2)

    aggregated = aggregate_worker_scripts([code1, code2])
    assert "import bpy" in aggregated
    assert "bpy.ops.import_anim.bvh" in aggregated
    assert "bpy.ops.export_anim.bvh" in aggregated
    assert "LeftFoot" in aggregated
    assert "Spine" in aggregated
    tree = ast.parse(aggregated)
    assert tree is not None

def test_dynamic_qa_judge():
    spec = AgentSpecification(
        agent_id="spec-foot",
        role="LeftFoot Contact Specialist",
        target_bones=["LeftFoot"],
        target_frames=[0, 10],
    )
    valid_script = generate_multi_agent_script("", [spec])
    is_valid, err = validate_qa_script(valid_script, [spec])
    assert is_valid is True
    assert err == ""

    syntax_bad_script = "import bpy\ndef broken_function("
    is_valid, err = validate_qa_script(syntax_bad_script)
    assert is_valid is False
    assert "SyntaxError" in err

    missing_bpy = valid_script.replace("import bpy", "import math")
    is_valid, err = validate_qa_script(missing_bpy)
    assert is_valid is False
    assert "must import 'bpy'" in err

    prohibited_script = valid_script + "\nimport subprocess\nsubprocess.run(['rm', '-rf', '/'])"
    is_valid, err = validate_qa_script(prohibited_script)
    assert is_valid is False
    assert "Prohibited import 'subprocess'" in err

def test_runs_end_to_end(test_setup):
    client, db_path, original_asset_id, _ = test_setup
    req = {
        "session_id": "session-multi-01",
        "plan_id": "plan-multi-01",
        "approval_id": "approval-multi-01",
    }
    response = client.post("/runs", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert "asset_id" in data
    repaired_asset_id = data["asset_id"]
    assert repaired_asset_id != original_asset_id
    assert data["repaired_file_url"] == f"/bvh/{repaired_asset_id}"
    assert "script_code" in data
    assert "LeftFoot" in data["script_code"]
    assert data["metrics"]["qa_passed"] is True

    with get_db(db_path) as conn:
        repaired_asset = get_asset(conn, repaired_asset_id)
        assert repaired_asset is not None
        assert repaired_asset.filename == "repaired_test_motion.bvh"
        assert os.path.exists(repaired_asset.file_path)

        session = get_workflow_session(conn, "session-multi-01")
        assert session is not None
        assert session.lifecycle_state == LifecycleState.COMPLETED
        assert session.asset_id == repaired_asset_id

    bvh_resp = client.get(f"/bvh/{repaired_asset_id}")
    assert bvh_resp.status_code == 200

def test_run_blender_user_edited_script(test_setup):
    client, db_path, asset_id, _ = test_setup
    custom_script = BLENDER_BOILERPLATE.format(
        fix_logic="""if armature and armature.pose:
    for b in armature.pose.bones:
        b.location.z = 0.0"""
    )
    req = {
        "session_id": "session-multi-01",
        "plan_id": "plan-multi-01",
        "approval_id": "approval-multi-01",
        "bvh_id": asset_id,
        "script_code": custom_script,
    }
    response = client.post("/run_blender", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert "asset_id" in data
    new_asset_id = data["asset_id"]

    with get_db(db_path) as conn:
        asset = get_asset(conn, new_asset_id)
        assert asset is not None
        assert asset.filename == "edited_test_motion.bvh"

def test_batch_orchestrator_dynamic_agents():
    temp_dir = tempfile.mkdtemp()
    test_bvh_file = os.path.join(temp_dir, "batch_test.bvh")
    with open(test_bvh_file, "w", encoding="utf-8") as f:
        f.write(SAMPLE_BVH)

    batch_file = BatchFile(
        id="batch-file-01",
        original_name="batch_test.bvh",
        path=test_bvh_file,
        status=Status.PENDING,
    )
    class MockInstruction:
        prompt = "Fix foot sliding and smooth jitter"

    import asyncio
    success = asyncio.run(
        process_batch_file(batch_file, MockInstruction(), SAMPLE_BVH, temp_dir)
    )
    assert success is True
    assert batch_file.status == Status.COMPLETED
    assert batch_file.output_path is not None
    assert os.path.exists(batch_file.output_path)
    shutil.rmtree(temp_dir, ignore_errors=True)

def test_runs_unapproved_rejection(test_setup):
    client, _, _, _ = test_setup
    req = {
        "session_id": "session-multi-01",
        "plan_id": "plan-multi-01",
        "approval_id": "invalid-approval-id",
    }
    response = client.post("/runs", json=req)
    assert response.status_code == 409

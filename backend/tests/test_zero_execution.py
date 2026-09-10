import os
import uuid
os.environ["TESTING"] = "1"
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from main import app
from database import (
    init_db,
    get_db,
    insert_asset,
    insert_analysis,
    insert_workflow_session,
    insert_repair_plan,
    approve_plan_transaction,
)
from models import (
    Asset,
    Analysis,
    WorkflowSession,
    RepairPlan,
    Approval,
    LifecycleState,
    AnalysisStatus,
    BVHMetadata,
    Finding,
    AnomalyType,
    Severity,
    BodyPart,
)
from detector import compute_roster_hash


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)

    import database
    orig_path = database.DB_PATH
    database.DB_PATH = path

    with TestClient(app) as test_client:
        yield test_client, path

    database.DB_PATH = orig_path
    if os.path.exists(path):
        os.remove(path)


ZERO_BVH = """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  End Site
  {
    OFFSET 0.0 0.0 0.0
  }
}
MOTION
Frames: 5
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0
50.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0
"""


def setup_approved_state(db_path: str):
    bvh_path = os.path.join(tempfile.gettempdir(), f"asset_zero_{uuid.uuid4().hex}.bvh")
    with open(bvh_path, "w", encoding="utf-8") as f:
        f.write(ZERO_BVH)

    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_zero",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition", "Zrotation", "Xrotation", "Yrotation"]},
        total_channels=6,
        frame_count=5,
        frame_time=0.033333,
        duration_seconds=0.166665,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-zero",
        filename="test.bvh",
        file_path=bvh_path,
        file_size_bytes=len(ZERO_BVH),
        content_hash="content_zero",
        skeleton_signature="sig_zero",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )
    finding = Finding(
        finding_id="f1",
        analysis_id="analysis-zero",
        affected_joint="Hips",
        affected_body_part=BodyPart.PELVIS,
        frame_start=2,
        frame_end=2,
        peak_frame=2,
        time_start=0.066666,
        time_end=0.066666,
        anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
        severity=Severity.HIGH,
        confidence=0.99,
        evidence={"velocity": 1500.0},
        explanation="Root translation jump",
        created_at="2026-09-04T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="analysis-zero",
        asset_id="asset-zero",
        content_hash="content_zero",
        skeleton_signature="sig_zero",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="analysis_hash_zero",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[finding],
        created_at="2026-09-04T12:00:00Z",
    )
    session = WorkflowSession(
        session_id="session-zero",
        asset_id="asset-zero",
        analysis_id="analysis-zero",
        lifecycle_state=LifecycleState.AWAITING_APPROVAL,
        created_at="2026-09-04T12:00:00Z",
        updated_at="2026-09-04T12:00:00Z",
    )
    future_ts = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    now_ts = datetime.now(timezone.utc).isoformat()
    plan = RepairPlan(
        plan_id="plan-zero",
        session_id="session-zero",
        analysis_id="analysis-zero",
        analysis_hash="analysis_hash_zero",
        version=1,
        selected_finding_ids=["f1"],
        proposed_roster=[],
        status="PENDING",
        created_at=now_ts,
        expires_at=future_ts,
    )
    roster_hash = compute_roster_hash([])
    approval = Approval(
        approval_id="appr-zero",
        session_id="session-zero",
        plan_id="plan-zero",
        repair_plan_version=1,
        analysis_hash="analysis_hash_zero",
        selected_finding_ids=["f1"],
        roster_hash=roster_hash,
        approved_by="authenticated_user",
        approved_at=now_ts,
        valid_until=future_ts,
    )

    with get_db(db_path) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)
        insert_workflow_session(conn, session)
        insert_repair_plan(conn, plan)
        approve_plan_transaction(conn, approval, now_ts)


def test_zero_execution_guarantees(client, monkeypatch):
    test_client, db_path = client

    agent_mock = MagicMock()
    runner_mock = MagicMock()
    subprocess_run_mock = MagicMock()
    subprocess_popen_mock = MagicMock()
    blender_mock = MagicMock()

    try:
        monkeypatch.setattr("google.adk.Agent.__init__", agent_mock)
    except AttributeError:
        pass
    try:
        monkeypatch.setattr("google.adk.runners.InMemoryRunner.run_debug", runner_mock)
    except AttributeError:
        pass

    monkeypatch.setattr("subprocess.run", subprocess_run_mock)
    monkeypatch.setattr("subprocess.Popen", subprocess_popen_mock)
    monkeypatch.setattr("blender.execute_blender_script", blender_mock)

    res = test_client.post(
        "/runs",
        json={"session_id": "none", "plan_id": "none", "approval_id": "none"},
    )
    assert res.status_code == 409

    res_gen = test_client.post("/generate_code", data={"bvh_id": "test"})
    assert res_gen.status_code == 409

    res_blender = test_client.post(
        "/run_blender",
        json={"bvh_id": "test", "script_code": "import bpy"},
    )
    assert res_blender.status_code == 409

    setup_approved_state(db_path)

    res_run = test_client.post(
        "/runs",
        json={
            "session_id": "session-zero",
            "plan_id": "plan-zero",
            "approval_id": "appr-zero",
        },
    )
    assert res_run.status_code == 200
    assert res_run.json().get("status") in ("APPROVED", "COMPLETED")

    res_gen_appr = test_client.post(
        "/generate_code",
        data={
            "session_id": "session-zero",
            "plan_id": "plan-zero",
            "approval_id": "appr-zero",
            "bvh_id": "asset-zero",
        },
    )
    assert res_gen_appr.status_code == 200
    assert res_gen_appr.json().get("status") == "APPROVED"

    res_blender_appr = test_client.post(
        "/run_blender",
        json={
            "session_id": "session-zero",
            "plan_id": "plan-zero",
            "approval_id": "appr-zero",
            "bvh_id": "asset-zero",
            "script_code": "import bpy",
        },
    )
    assert res_blender_appr.status_code == 200
    assert res_blender_appr.json().get("status") in ("APPROVED", "COMPLETED")

    res_batch = test_client.post(
        "/batch_process",
        data={"prompt": "test batch prompt"},
    )
    assert res_batch.status_code in (404, 501)

    assert agent_mock.call_count == 0
    assert runner_mock.call_count == 0
    assert subprocess_run_mock.call_count == 0
    assert subprocess_popen_mock.call_count == 0

    with get_db(db_path) as conn:
        from database import get_workflow_session
        session = get_workflow_session(conn, "session-zero")
        assert session.lifecycle_state in (LifecycleState.APPROVED, LifecycleState.COMPLETED)

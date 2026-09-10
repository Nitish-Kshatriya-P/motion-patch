import os
os.environ["TESTING"] = "1"
import tempfile
import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

try:
    import backend.agent as agent_module
except ModuleNotFoundError:
    import agent as agent_module
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
    compute_roster_hash,
)

@pytest.fixture
def dynamic_client():
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

def test_static_agents_removed():
    assert not hasattr(agent_module, "supervisor")
    assert not hasattr(agent_module, "contact_worker")
    assert not hasattr(agent_module, "kinematics_worker")
    assert not hasattr(agent_module, "qa_agent")

def test_distinct_prompts_generate_distinct_rosters():
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_test",
        root_name="Hips",
        joints=["Hips", "Spine", "LeftFoot", "RightFoot", "LeftArm"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=120,
        frame_time=0.033333,
        duration_seconds=4.0,
        skeleton_scale=100.0,
    )
    foot_finding = Finding(
        finding_id="find-foot-1",
        analysis_id="analysis-1",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=30,
        frame_end=65,
        time_start=1.0,
        time_end=2.16,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.95,
        evidence={"velocity": 12.4},
        explanation="Planted foot sliding on ground",
    )
    spine_finding = Finding(
        finding_id="find-spine-1",
        analysis_id="analysis-1",
        affected_joint="Spine",
        affected_body_part=BodyPart.SPINE,
        frame_start=70,
        frame_end=110,
        time_start=2.33,
        time_end=3.66,
        anomaly_type=AnomalyType.ROTATION_JITTER,
        severity=Severity.MEDIUM,
        confidence=0.88,
        evidence={"jitter_energy": 8.1},
        explanation="Spine rotation jitter",
    )

    roster_foot = agent_module.synthesize_agent_roster(
        prompt="Pin the foot firmly to the ground plane to prevent foot sliding",
        findings=[foot_finding],
        metadata=meta,
    )
    roster_spine = agent_module.synthesize_agent_roster(
        prompt="Smooth rotation jitter in the spine using Catmull-Rom filtering",
        findings=[spine_finding],
        metadata=meta,
    )
    roster_arm = agent_module.synthesize_agent_roster(
        prompt="Clean up erratic left arm trajectories",
        findings=[],
        metadata=meta,
    )

    assert len(roster_foot) > 0
    assert len(roster_spine) > 0
    assert len(roster_arm) > 0

    agent_foot = roster_foot[0]
    agent_spine = roster_spine[0]
    agent_arm = roster_arm[0]

    assert agent_foot.role != agent_spine.role
    assert agent_spine.role != agent_arm.role
    assert "Contact" in agent_foot.role or "Foot" in agent_foot.role
    assert "Jitter" in agent_spine.role or "Smoother" in agent_spine.role or "Spine" in agent_spine.role
    assert "Arm" in agent_arm.role or "Limb" in agent_arm.role

    assert "LeftFoot" in agent_foot.target_bones
    assert "Spine" in agent_spine.target_bones
    assert any("Arm" in bone for bone in agent_arm.target_bones)

    assert agent_foot.target_frames == [30, 65]
    assert agent_spine.target_frames == [70, 110]
    assert agent_arm.target_frames == [0, 120]

    assert agent_foot.system_instruction != agent_spine.system_instruction
    assert "query_clickhouse_rag" in agent_foot.tools
    assert "query_clickhouse_rag" in agent_spine.tools

def test_instantiate_dynamic_agent():
    spec = AgentSpecification(
        agent_id="agent-dyn-123",
        role="LeftAnkle Ground Contact Specialist",
        assigned_joints=["LeftAnkle"],
        target_bones=["LeftAnkle"],
        target_frames=[20, 50],
        tools=["query_clickhouse_rag"],
        status="SPAWNED",
        system_instruction="Fix LeftAnkle ground sliding using IK.",
    )
    agent_instance = agent_module.instantiate_dynamic_agent(spec)
    assert agent_instance is not None
    assert "leftankle" in agent_instance.name.lower()
    assert agent_instance.instruction == spec.system_instruction
    assert len(agent_instance.tools) == 1
    assert agent_instance.tools[0] == agent_module.query_clickhouse_rag

def setup_test_approved_session(db_path: str, session_id: str = "sess-dyn-1"):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig-dyn",
        root_name="Hips",
        joints=["Hips", "LeftFoot"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=80,
        frame_time=0.033333,
        duration_seconds=2.66,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-dyn-1",
        filename="motion.bvh",
        file_path="/tmp/motion.bvh",
        file_size_bytes=2048,
        content_hash="hash-dyn",
        skeleton_signature="sig-dyn",
        metadata=meta,
        created_at="2026-09-05T10:00:00Z",
    )
    finding = Finding(
        finding_id="find-f1",
        analysis_id="analysis-dyn-1",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=25,
        frame_end=60,
        time_start=0.83,
        time_end=2.0,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.91,
        evidence={},
        explanation="Planted foot slip",
    )
    analysis = Analysis(
        analysis_id="analysis-dyn-1",
        asset_id="asset-dyn-1",
        content_hash="hash-dyn",
        skeleton_signature="sig-dyn",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash-dyn",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[finding],
        created_at="2026-09-05T10:00:00Z",
    )
    session = WorkflowSession(
        session_id=session_id,
        asset_id="asset-dyn-1",
        analysis_id="analysis-dyn-1",
        lifecycle_state=LifecycleState.AWAITING_APPROVAL,
        created_at="2026-09-05T10:00:00Z",
        updated_at="2026-09-05T10:00:00Z",
    )
    future_ts = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    now_ts = datetime.now(timezone.utc).isoformat()
    plan = RepairPlan(
        plan_id="plan-dyn-1",
        session_id=session_id,
        analysis_id="analysis-dyn-1",
        analysis_hash="ahash-dyn",
        version=1,
        selected_finding_ids=["find-f1"],
        proposed_roster=[],
        status="PENDING",
        created_at=now_ts,
        expires_at=future_ts,
    )
    roster_hash = compute_roster_hash([])
    approval = Approval(
        approval_id="appr-dyn-1",
        session_id=session_id,
        plan_id="plan-dyn-1",
        repair_plan_version=1,
        analysis_hash="ahash-dyn",
        selected_finding_ids=["find-f1"],
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

def test_generate_code_dispatches_synthesizer(dynamic_client):
    client, db_path = dynamic_client
    session_id = "sess-gen-test"
    setup_test_approved_session(db_path, session_id=session_id)

    res = client.post(
        "/generate_code",
        data={
            "session_id": session_id,
            "plan_id": "plan-dyn-1",
            "approval_id": "appr-dyn-1",
            "bvh_id": "asset-dyn-1",
            "prompt": "Pin LeftFoot to ground to stop sliding",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "APPROVED"
    assert "roster" in data
    assert data["roster_count"] >= 1
    first_agent = data["roster"][0]
    assert "LeftFoot" in first_agent["target_bones"]
    assert first_agent["status"] == "SPAWNED"
    assert "query_clickhouse_rag" in first_agent["tools"]

def test_agent_stream_sse(dynamic_client):
    client, db_path = dynamic_client
    session_id = "sess-sse-test"
    setup_test_approved_session(db_path, session_id=session_id)

    gen_res = client.post(
        "/generate_code",
        data={
            "session_id": session_id,
            "plan_id": "plan-dyn-1",
            "approval_id": "appr-dyn-1",
            "bvh_id": "asset-dyn-1",
            "prompt": "Pin LeftFoot to ground",
        },
    )
    assert gen_res.status_code == 200

    stream_res = client.get(f"/sessions/{session_id}/agent-stream?auto_close=true")
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]

    lines = stream_res.text.strip().split("\n")
    events = []
    for line in lines:
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            events.append(payload)

    event_types = [e.get("event") for e in events]
    assert "CONNECTED" in event_types
    assert "AGENT_SPAWNED" in event_types
    assert "AGENT_STATUS" in event_types
    assert "ROSTER_COMPLETE" in event_types

    spawned = [e for e in events if e.get("event") == "AGENT_SPAWNED"]
    assert len(spawned) >= 1
    assert "role" in spawned[0]["agent"]
    assert "LeftFoot" in spawned[0]["agent"]["target_bones"]

    statuses = [e.get("status") for e in events if e.get("event") == "AGENT_STATUS"]
    assert "THINKING" in statuses
    assert "COMPLETED" not in statuses

def test_parse_kinematic_intent_scope_and_restrictions():
    intent_arm = agent_module.parse_kinematic_intent("only fix the arm motion")
    assert intent_arm["allow_arm"] is True
    assert intent_arm["allow_foot"] is False
    assert intent_arm["allow_jitter"] is False
    assert intent_arm["allow_root"] is False

    intent_foot = agent_module.parse_kinematic_intent("only fix the left foot frames 40 to 80")
    assert intent_foot["allow_foot"] is True
    assert intent_foot["allow_jitter"] is False
    assert intent_foot["allow_root"] is False
    assert intent_foot["frame_start"] == 40
    assert intent_foot["frame_end"] == 80

    intent_ignore = agent_module.parse_kinematic_intent("fix motion but ignore spine and don't touch root")
    assert intent_ignore["allow_jitter"] is False
    assert intent_ignore["allow_root"] is False
    assert intent_ignore["allow_foot"] is True

def test_approval_verify_against_methods():
    now_ts = datetime.now(timezone.utc).isoformat()
    future_ts = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    approval = Approval(
        approval_id="app-1",
        session_id="sess-1",
        plan_id="plan-1",
        repair_plan_version=1,
        analysis_hash="ahash",
        selected_finding_ids=["f1"],
        selected_joints=["LeftFoot"],
        user_prompt="fix foot",
        roster_hash=compute_roster_hash([]),
        approved_by="user",
        approved_at=now_ts,
        valid_until=future_ts,
    )
    plan = RepairPlan(
        plan_id="plan-1",
        session_id="sess-1",
        analysis_id="an-1",
        analysis_hash="ahash",
        version=1,
        selected_finding_ids=["f1"],
        selected_joints=["LeftFoot"],
        user_prompt="fix foot",
        proposed_roster=[],
        status="PENDING",
        created_at=now_ts,
        expires_at=future_ts,
    )
    analysis = Analysis(
        analysis_id="an-1",
        asset_id="ass-1",
        content_hash="chash",
        skeleton_signature="sig",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash",
        status=AnalysisStatus.FINDINGS,
        findings=[],
        created_at=now_ts,
    )
    session = WorkflowSession(
        session_id="sess-1",
        asset_id="ass-1",
        analysis_id="an-1",
        lifecycle_state=LifecycleState.APPROVED,
        created_at=now_ts,
        updated_at=now_ts,
    )
    assert approval.verify_against(session, plan, analysis) is None

    approval_expired = approval.model_copy(update={"valid_until": past_ts})
    assert "expired" in approval_expired.verify_against(session, plan, analysis).lower()

    approval_mismatch = approval.model_copy(update={"repair_plan_version": 2})
    assert "version" in approval_mismatch.verify_against(session, plan, analysis).lower()

def test_selective_body_part_and_custom_instruction_synthesis():
    findings = [
        {"affected_joint": "LeftFoot", "anomaly_type": "PLANTED_FOOT_SLIDING", "frame_start": 10, "frame_end": 20},
        {"affected_joint": "RightFoot", "anomaly_type": "PLANTED_FOOT_SLIDING", "frame_start": 30, "frame_end": 40},
        {"affected_joint": "Spine", "anomaly_type": "ROTATION_JITTER", "frame_start": 5, "frame_end": 50},
        {"affected_joint": "Hips", "anomaly_type": "ROOT_DISCONTINUITY", "frame_start": 1, "frame_end": 15},
    ]
    roster_left_foot = agent_module.synthesize_agent_roster(findings=findings, selected_joints=["LeftFoot"])
    assert len(roster_left_foot) == 1
    assert roster_left_foot[0].assigned_joints == ["LeftFoot"]

    roster_spine_instruction = agent_module.synthesize_agent_roster(prompt="Smooth spine jitter", findings=findings)
    assert len(roster_spine_instruction) == 1
    assert "Spine" in roster_spine_instruction[0].assigned_joints

    roster_both_feet = agent_module.synthesize_agent_roster(findings=findings, selected_joints=["LeftFoot", "RightFoot"])
    assert len(roster_both_feet) == 1
    assert "LeftFoot" in roster_both_feet[0].assigned_joints
    assert "RightFoot" in roster_both_feet[0].assigned_joints


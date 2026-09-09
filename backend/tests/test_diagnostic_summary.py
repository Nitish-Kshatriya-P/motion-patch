import os
os.environ["TESTING"] = "1"
import tempfile
import pytest
from fastapi.testclient import TestClient
from main import app
from database import init_db, get_db, insert_asset, insert_analysis, insert_workflow_session
from models import (
    Asset,
    Analysis,
    Finding,
    WorkflowSession,
    LifecycleState,
    AnalysisStatus,
    AnomalyType,
    Severity,
    BodyPart,
    BVHMetadata,
)
from detector import generate_diagnostic_summary


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


def test_generate_diagnostic_summary_clean():
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_clean",
        root_name="Hips",
        joints=["Hips", "LeftLeg"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=180,
        frame_time=0.033333,
        duration_seconds=6.0,
        skeleton_scale=100.0,
    )
    analysis = Analysis(
        analysis_id="an_clean",
        asset_id="ast_clean",
        content_hash="ch_clean",
        skeleton_signature="sig_clean",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ah_clean",
        status=AnalysisStatus.CLEAN,
        up_axis="Y",
        findings=[],
        created_at="2026-09-05T12:00:00Z",
    )
    summary = generate_diagnostic_summary(analysis, meta)
    assert "Kinematic analysis complete" in summary
    assert "No jitter, foot sliding, or root discontinuities detected" in summary
    assert "180 frames" in summary
    assert "6.00s" in summary


def test_generate_diagnostic_summary_with_findings():
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_dirty",
        root_name="Hips",
        joints=["Hips", "LeftFoot", "RightArm"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=100,
        frame_time=0.033333,
        duration_seconds=3.33,
        skeleton_scale=100.0,
    )
    finding1 = Finding(
        finding_id="f1",
        analysis_id="an_dirty",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=10,
        frame_end=35,
        time_start=0.33,
        time_end=1.16,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.9,
        evidence={"drift": 5.2},
        detector_version="1.0.0",
        explanation="Planted foot sliding detected on LeftFoot.",
        created_at="2026-09-05T12:00:00Z",
    )
    finding2 = Finding(
        finding_id="f2",
        analysis_id="an_dirty",
        affected_joint="RightArm",
        affected_body_part=BodyPart.ARM,
        frame_start=40,
        frame_end=60,
        time_start=1.33,
        time_end=2.0,
        anomaly_type=AnomalyType.ROTATION_JITTER,
        severity=Severity.MEDIUM,
        confidence=0.85,
        evidence={"mad": 3.1},
        detector_version="1.0.0",
        explanation="Rotation jitter detected on RightArm.",
        created_at="2026-09-05T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="an_dirty",
        asset_id="ast_dirty",
        content_hash="ch_dirty",
        skeleton_signature="sig_dirty",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ah_dirty",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[finding1, finding2],
        created_at="2026-09-05T12:00:00Z",
    )
    summary = generate_diagnostic_summary(analysis, meta)
    assert "Kinematic analysis detected 2 anomalies across 2 joints" in summary
    assert "LeftFoot: frames 10-35 (PLANTED_FOOT_SLIDING, HIGH)" in summary
    assert "RightArm: frames 40-60 (ROTATION_JITTER, MEDIUM)" in summary


def test_analysis_summary_endpoint(client):
    test_client, db_path = client
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_ep",
        root_name="Hips",
        joints=["Hips", "LeftFoot"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=90,
        frame_time=0.033333,
        duration_seconds=3.0,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="ast_ep",
        filename="walk.bvh",
        file_path="/tmp/walk.bvh",
        file_size_bytes=1000,
        content_hash="ch_ep",
        skeleton_signature="sig_ep",
        metadata=meta,
        created_at="2026-09-05T12:00:00Z",
    )
    finding = Finding(
        finding_id="f_ep",
        analysis_id="an_ep",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=15,
        frame_end=30,
        time_start=0.5,
        time_end=1.0,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.95,
        evidence={"drift": 4.0},
        detector_version="1.0.0",
        explanation="Planted foot sliding on LeftFoot",
        created_at="2026-09-05T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="an_ep",
        asset_id="ast_ep",
        content_hash="ch_ep",
        skeleton_signature="sig_ep",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ah_ep",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[finding],
        diagnostic_summary=None,
        created_at="2026-09-05T12:00:00Z",
    )

    with get_db(db_path) as conn:
        with conn:
            insert_asset(conn, asset)
            insert_analysis(conn, analysis)

    res = test_client.get("/analyses/an_ep/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_id"] == "an_ep"
    assert "LeftFoot: frames 15-30" in data["summary"]
    assert "LeftFoot" in data["broken_joints"]
    assert len(data["frame_intervals"]) == 1
    assert data["frame_intervals"][0]["frame_start"] == 15
    assert data["frame_intervals"][0]["frame_end"] == 30
    assert data["duration_seconds"] == 3.0

    res_text = test_client.get("/analyses/an_ep/summary?format=text")
    assert res_text.status_code == 200
    assert "text/plain" in res_text.headers["content-type"]
    assert "Kinematic analysis detected" in res_text.text

import os
os.environ["TESTING"] = "1"
import io
import tempfile
import pytest
from fastapi.testclient import TestClient
from main import app
from database import init_db, get_db, insert_asset, insert_analysis, insert_workflow_session
from models import (
    Asset,
    Analysis,
    WorkflowSession,
    LifecycleState,
    AnalysisStatus,
    BVHMetadata,
)


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


def test_list_sessions_endpoint(client):
    test_client, db_path = client
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_sess",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=120,
        frame_time=0.033333,
        duration_seconds=4.0,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="ast_sess_1",
        filename="session_file.bvh",
        file_path="/tmp/session_file.bvh",
        file_size_bytes=2048,
        content_hash="ch_sess_1",
        skeleton_signature="sig_sess",
        metadata=meta,
        created_at="2026-09-05T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="an_sess_1",
        asset_id="ast_sess_1",
        content_hash="ch_sess_1",
        skeleton_signature="sig_sess",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ah_sess_1",
        status=AnalysisStatus.CLEAN,
        up_axis="Y",
        findings=[],
        diagnostic_summary="Kinematic analysis complete: Clean.",
        created_at="2026-09-05T12:00:00Z",
    )
    session = WorkflowSession(
        session_id="sess_1",
        asset_id="ast_sess_1",
        analysis_id="an_sess_1",
        lifecycle_state=LifecycleState.COMPLETED,
        created_at="2026-09-05T12:00:00Z",
        updated_at="2026-09-05T12:00:00Z",
    )

    with get_db(db_path) as conn:
        with conn:
            insert_asset(conn, asset)
            insert_analysis(conn, analysis)
            insert_workflow_session(conn, session)

    res = test_client.get("/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert isinstance(sessions, list)
    assert len(sessions) >= 1
    found = next((s for s in sessions if s["session_id"] == "sess_1"), None)
    assert found is not None
    assert found["filename"] == "session_file.bvh"
    assert found["lifecycle_state"] == "COMPLETED"
    assert found["duration_seconds"] == 4.0
    assert found["frame_count"] == 120
    assert found["findings_count"] == 0


def test_uuid_session_title_generation_and_patch(client):
    test_client, db_path = client
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_uuid",
        root_name="Hips",
        joints=["LeftLeg", "Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"], "LeftLeg": ["Zrotation"]},
        total_channels=4,
        frame_count=20,
        frame_time=0.033333,
        duration_seconds=0.67,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="ast_uuid_1",
        filename="092cb236-75a4-481a-bba9-7281ca418847.bvh",
        file_path="/tmp/092cb236-75a4-481a-bba9-7281ca418847.bvh",
        file_size_bytes=1024,
        content_hash="ch_uuid_1",
        skeleton_signature="sig_uuid",
        metadata=meta,
        created_at="2026-09-06T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="an_uuid_1",
        asset_id="ast_uuid_1",
        content_hash="ch_uuid_1",
        skeleton_signature="sig_uuid",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ah_uuid_1",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[],
        diagnostic_summary="Kinematic analysis detected 1 anomaly across 1 joint:\n- LeftLeg: frames 9-15 (ROTATION_JITTER, MEDIUM)",
        created_at="2026-09-06T12:00:00Z",
    )
    session = WorkflowSession(
        session_id="sess_uuid_1",
        asset_id="ast_uuid_1",
        analysis_id="an_uuid_1",
        lifecycle_state=LifecycleState.REVIEWING_FINDINGS,
        created_at="2026-09-06T12:00:00Z",
        updated_at="2026-09-06T12:00:00Z",
    )

    with get_db(db_path) as conn:
        with conn:
            insert_asset(conn, asset)
            insert_analysis(conn, analysis)
            insert_workflow_session(conn, session)

    res = test_client.get("/sessions")
    assert res.status_code == 200
    sessions = res.json()
    found = next((s for s in sessions if s["session_id"] == "sess_uuid_1"), None)
    assert found is not None
    assert found["title"] == "LeftLeg Rotation Jitter"

    patch_res = test_client.patch(
        "/sessions/sess_uuid_1/title",
        json={"title": "Custom Hero Walk Repair"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Custom Hero Walk Repair"

    res_after = test_client.get("/sessions")
    found_after = next((s for s in res_after.json() if s["session_id"] == "sess_uuid_1"), None)
    assert found_after["title"] == "Custom Hero Walk Repair"


def test_session_upload_limit_enforced(client):
    test_client, db_path = client
    bvh_content = b"""HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    End Site
    {
        OFFSET 0.0 -5.0 0.0
    }
}
MOTION
Frames: 2
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0
"""
    res1 = test_client.post(
        "/upload",
        files={"file": ("test_1.bvh", io.BytesIO(bvh_content), "application/octet-stream")},
    )
    assert res1.status_code == 200
    session_id = res1.json()["session_id"]
    assert res1.json()["uploaded_files_count"] == 1

    for i in range(2, 6):
        res = test_client.post(
            "/upload",
            files={"file": (f"test_{i}.bvh", io.BytesIO(bvh_content), "application/octet-stream")},
            data={"session_id": session_id},
        )
        assert res.status_code == 200
        assert res.json()["session_id"] == session_id
        assert res.json()["uploaded_files_count"] == i

    res6 = test_client.post(
        "/upload",
        files={"file": ("test_6.bvh", io.BytesIO(bvh_content), "application/octet-stream")},
        data={"session_id": session_id},
    )
    assert res6.status_code == 400
    assert "Upload limit reached" in res6.json()["detail"]

    files_res = test_client.get(f"/sessions/{session_id}/files")
    assert files_res.status_code == 200
    files_data = files_res.json()
    assert files_data["count"] == 5
    assert files_data["max_files"] == 5
    assert files_data["remaining"] == 0
    assert len(files_data["files"]) == 5


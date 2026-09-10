import os
os.environ["TESTING"] = "1"
import io
import tempfile
import pytest
from fastapi.testclient import TestClient

from main import app, QUARANTINE_DIR, UPLOAD_DIR
from database import init_db
import database

CLEAN_BVH = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftFoot
    {
        OFFSET 0.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -5.0 0.0
        }
    }
}
MOTION
Frames: 5
Frame Time: 0.033333
0.0 15.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 15.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 15.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 15.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 15.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
"""

JITTER_BVH = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftLeg
    {
        OFFSET -5.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -10.0 0.0
        }
    }
}
MOTION
Frames: 20
Frame Time: 0.033333
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   -35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   -35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   -35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   35.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
"""


@pytest.fixture
def api_client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)

    orig_path = database.DB_PATH
    database.DB_PATH = path

    with TestClient(app) as test_client:
        yield test_client, path

    database.DB_PATH = orig_path
    if os.path.exists(path):
        os.remove(path)


def test_upload_and_clean_analysis_flow(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(CLEAN_BVH.encode("utf-8"))

    res = client.post(
        "/upload",
        files={"file": ("clean.bvh", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "asset_id" in data
    assert "session_id" in data
    assert "analysis_id" in data
    assert data["status"] == "CLEAN"
    assert data["findings_count"] == 0

    asset_res = client.get(f"/assets/{data['asset_id']}")
    assert asset_res.status_code == 200
    assert asset_res.json()["filename"] == "clean.bvh"

    analysis_res = client.get(f"/analyses/{data['analysis_id']}")
    assert analysis_res.status_code == 200
    assert analysis_res.json()["status"] == "CLEAN"
    assert analysis_res.json()["up_axis"] == "Y"

    session_res = client.get(f"/workflow-sessions/{data['session_id']}")
    assert session_res.status_code == 200
    assert session_res.json()["lifecycle_state"] == "COMPLETED"


def test_upload_with_findings_plan_and_approval_flow(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    res = client.post(
        "/upload",
        files={"file": ("jitter.bvh", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "FINDINGS"
    assert data["findings_count"] > 0
    session_id = data["session_id"]
    analysis_id = data["analysis_id"]

    analysis_res = client.get(f"/analyses/{analysis_id}")
    assert analysis_res.status_code == 200
    findings = analysis_res.json()["findings"]
    assert len(findings) > 0
    selected_fids = [f["finding_id"] for f in findings]

    plan_res = client.post(
        f"/analyses/{analysis_id}/repair-plan",
        json={"session_id": session_id, "selected_finding_ids": selected_fids},
    )
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    assert plan_data["status"] == "PENDING"
    assert plan_data["proposed_roster"] == []
    plan_id = plan_data["plan_id"]

    sess_check = client.get(f"/workflow-sessions/{session_id}")
    assert sess_check.json()["lifecycle_state"] == "AWAITING_APPROVAL"

    approve_res = client.post(
        f"/repair-plans/{plan_id}/approve",
        json={
            "session_id": session_id,
            "plan_id": plan_id,
            "repair_plan_version": 1,
            "selected_finding_ids": selected_fids,
            "confirmed": True,
        },
    )
    assert approve_res.status_code == 200
    appr_data = approve_res.json()
    approval_id = appr_data["approval_id"]

    sess_approved = client.get(f"/workflow-sessions/{session_id}")
    assert sess_approved.json()["lifecycle_state"] == "APPROVED"

    run_res = client.post(
        "/runs",
        json={
            "session_id": session_id,
            "plan_id": plan_id,
            "approval_id": approval_id,
        },
    )
    assert run_res.status_code == 200, run_res.json()
    assert run_res.json()["status"] in ("APPROVED", "COMPLETED")


def test_plan_rejection_returns_to_reviewing_findings(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    res = client.post(
        "/upload",
        files={"file": ("jitter.bvh", file_bytes, "application/octet-stream")},
    )
    data = res.json()
    session_id = data["session_id"]
    analysis_id = data["analysis_id"]

    plan_res = client.post(
        f"/analyses/{analysis_id}/repair-plan",
        json={"session_id": session_id, "selected_finding_ids": []},
    )
    plan_id = plan_res.json()["plan_id"]

    reject_res = client.post(
        f"/repair-plans/{plan_id}/reject",
        json={"session_id": session_id, "plan_id": plan_id},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "REJECTED"
    assert reject_res.json()["lifecycle_state"] == "REVIEWING_FINDINGS"

    sess = client.get(f"/workflow-sessions/{session_id}")
    assert sess.json()["lifecycle_state"] == "REVIEWING_FINDINGS"


def test_quarantine_cleanup_on_malformed_upload(api_client):
    client, _ = api_client
    bad_bytes = io.BytesIO(b"MALFORMED_DATA_NOT_BVH")

    initial_quarantine_count = len(os.listdir(QUARANTINE_DIR))

    res = client.post(
        "/upload",
        files={"file": ("corrupt.bvh", bad_bytes, "application/octet-stream")},
    )
    assert res.status_code == 400
    assert "BVH Validation Error" in res.json()["detail"]

    after_quarantine_count = len(os.listdir(QUARANTINE_DIR))
    assert after_quarantine_count == initial_quarantine_count


def test_streaming_upload_exceeding_25mb_aborted_and_quarantine_deleted(api_client):
    client, _ = api_client
    initial_quarantine_count = len(os.listdir(QUARANTINE_DIR))

    oversized_chunk = b"A" * (1024 * 1024)

    class OversizedReader:
        def __init__(self):
            self.bytes_sent = 0
            self.total = 26 * 1024 * 1024

        def read(self, size=-1):
            if self.bytes_sent >= self.total:
                return b""
            chunk_len = min(len(oversized_chunk), self.total - self.bytes_sent)
            self.bytes_sent += chunk_len
            return oversized_chunk[:chunk_len]

    res = client.post(
        "/upload",
        files={"file": ("oversized.bvh", OversizedReader(), "application/octet-stream")},
    )
    assert res.status_code == 413
    assert len(os.listdir(QUARANTINE_DIR)) == initial_quarantine_count


def test_failure_during_commit_rolls_back_and_deletes_promoted_file(api_client, monkeypatch):
    client, _ = api_client
    file_bytes = io.BytesIO(CLEAN_BVH.encode("utf-8"))

    def mock_insert_analysis(*args, **kwargs):
        raise RuntimeError("Simulated DB commit error")

    monkeypatch.setattr("main.insert_analysis", mock_insert_analysis)

    initial_uploads = set(os.listdir(UPLOAD_DIR))

    res = client.post(
        "/upload",
        files={"file": ("fail_commit.bvh", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 500
    assert "Database commit failed" in res.json()["detail"]

    after_uploads = set(os.listdir(UPLOAD_DIR))
    assert after_uploads == initial_uploads


def test_reanalyze_asset_invalidates_approvals_and_rejects_stale_execution(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    res = client.post(
        "/upload",
        files={"file": ("jitter_reanalyze.bvh", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 200
    data = res.json()
    session_id = data["session_id"]
    analysis_id = data["analysis_id"]
    asset_id = data["id"]
    findings = data["findings"]
    assert len(findings) > 0
    fids = [f["finding_id"] for f in findings]

    plan_res = client.post(
        f"/analyses/{analysis_id}/repair-plan",
        json={"session_id": session_id, "selected_finding_ids": fids},
    )
    assert plan_res.status_code == 200
    plan_id = plan_res.json()["plan_id"]

    approve_res = client.post(
        f"/repair-plans/{plan_id}/approve",
        json={
            "session_id": session_id,
            "plan_id": plan_id,
            "repair_plan_version": 1,
            "selected_finding_ids": fids,
            "confirmed": True,
        },
    )
    assert approve_res.status_code == 200
    approval_id = approve_res.json()["approval_id"]

    sess_approved = client.get(f"/workflow-sessions/{session_id}")
    assert sess_approved.json()["lifecycle_state"] == "APPROVED"
    assert sess_approved.json()["approval_id"] == approval_id
    assert sess_approved.json()["plan_id"] == plan_id

    reanalyze_res = client.post(f"/assets/{asset_id}/reanalyze?session_id={session_id}")
    assert reanalyze_res.status_code == 200
    reanalyze_data = reanalyze_res.json()
    assert reanalyze_data["analysis_id"] != analysis_id
    assert "coverage_records" in reanalyze_data
    assert isinstance(reanalyze_data["coverage_records"], list)

    sess_reset = client.get(f"/workflow-sessions/{session_id}")
    assert sess_reset.json()["lifecycle_state"] == "REVIEWING_FINDINGS"
    assert sess_reset.json()["approval_id"] is None
    assert sess_reset.json()["plan_id"] is None

    stale_run_res = client.post(
        "/runs",
        json={
            "session_id": session_id,
            "plan_id": plan_id,
            "approval_id": approval_id,
        },
    )
    assert stale_run_res.status_code == 409


def test_saved_and_reloaded_findings_match_identical_frames_and_joints(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    upload_res = client.post(
        "/upload",
        files={"file": ("jitter_sync.bvh", file_bytes, "application/octet-stream")},
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    analysis_id = upload_data["analysis_id"]
    upload_findings = upload_data["findings"]
    assert len(upload_findings) > 0

    summary_res = client.get(f"/analyses/{analysis_id}/summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert "coverage_records" in summary_data
    intervals = summary_data["frame_intervals"]
    assert len(intervals) == len(upload_findings)

    for orig, reloaded in zip(upload_findings, intervals):
        assert orig["finding_id"] == reloaded["finding_id"]
        assert orig["affected_joint"] == reloaded["affected_joint"]
        assert orig["affected_joint"] == reloaded["joint"]
        assert orig["frame_start"] == reloaded["frame_start"]
        assert orig["frame_end"] == reloaded["frame_end"]
        assert reloaded["display_frame_start"] == reloaded["frame_start"] + 1
        assert reloaded["display_frame_end"] == reloaded["frame_end"] + 1
        assert reloaded["peak_frame"] == orig.get("peak_frame", orig["frame_start"])
        assert reloaded["display_peak_frame"] == reloaded["peak_frame"] + 1
        assert reloaded["confidence"] == orig["confidence"]
        assert reloaded["verdict"] == orig.get("verdict")


def test_ai_verified_not_unconditionally_applied_without_confirmation(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    res = client.post(
        "/upload",
        files={"file": ("jitter_unverified.bvh", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 200
    data = res.json()
    findings = data["findings"]
    assert len(findings) > 0

    for f in findings:
        ev = f.get("evidence", {})
        if isinstance(ev, dict):
            assert ev.get("ai_verified") is not True
        assert f["confidence"] < 0.95


def test_human_feedback_api_review_actions_and_persistence(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    upload_res = client.post(
        "/upload",
        files={"file": ("jitter_feedback.bvh", file_bytes, "application/octet-stream")},
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    asset_id = upload_data["asset_id"]
    session_id = upload_data["session_id"]
    analysis_id = upload_data["analysis_id"]
    findings = upload_data["findings"]
    assert len(findings) > 0
    target_finding = findings[0]
    finding_id = target_finding["finding_id"]

    confirm_res = client.post(
        f"/analyses/{analysis_id}/findings/{finding_id}/review",
        json={"action": "confirm", "notes": "Verified genuine jitter defect", "split": "dev"},
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["action"] == "confirm"
    assert confirm_data["finding_id"] == finding_id
    assert confirm_data["asset_id"] == asset_id
    assert confirm_data["joint"] == target_finding["affected_joint"]

    missed_res = client.post(
        "/feedback",
        json={
            "asset_id": asset_id,
            "session_id": session_id,
            "analysis_id": analysis_id,
            "action": "mark_missed",
            "joint": "Hips",
            "frame_start": 2,
            "frame_end": 5,
            "anomaly_type": "ROOT_DISCONTINUITY",
            "notes": "Human identified root pop missed by filter",
            "split": "dev",
        },
    )
    assert missed_res.status_code == 200
    missed_data = missed_res.json()
    assert missed_data["action"] == "mark_missed"
    assert missed_data["joint"] == "Hips"

    uncertain_res = client.post(
        "/feedback",
        json={
            "asset_id": asset_id,
            "session_id": session_id,
            "analysis_id": analysis_id,
            "action": "mark_uncertain",
            "joint": target_finding["affected_joint"],
            "frame_start": 16,
            "frame_end": 18,
            "notes": "Ambiguous movement on boundary frames",
            "split": "dev",
        },
    )
    assert uncertain_res.status_code == 200
    assert uncertain_res.json()["action"] == "mark_uncertain"

    reject_res = client.post(
        "/feedback",
        json={
            "asset_id": asset_id,
            "session_id": session_id,
            "analysis_id": analysis_id,
            "action": "reject",
            "joint": target_finding["affected_joint"],
            "frame_start": 0,
            "frame_end": 4,
            "notes": "Normal stylistic motion",
            "split": "dev",
        },
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["action"] == "reject"

    list_res = client.get(f"/feedback?asset_id={asset_id}")
    assert list_res.status_code == 200
    feedbacks = list_res.json()
    assert len(feedbacks) == 4

    asset_list_res = client.get(f"/assets/{asset_id}/feedback")
    assert asset_list_res.status_code == 200
    assert len(asset_list_res.json()) == 4

    uncertain_filter_res = client.get(f"/feedback?asset_id={asset_id}&action=mark_uncertain")
    assert uncertain_filter_res.status_code == 200
    assert len(uncertain_filter_res.json()) == 1


def test_api_false_alarm_evaluation_excludes_uncertain(api_client):
    client, _ = api_client
    file_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))

    res = client.post(
        "/upload",
        files={"file": ("jitter_fa_eval.bvh", file_bytes, "application/octet-stream")},
    )
    assert res.status_code == 200
    data = res.json()
    asset_id = data["asset_id"]
    analysis_id = data["analysis_id"]
    findings = data["findings"]
    assert len(findings) > 0

    f0 = findings[0]
    client.post(
        f"/analyses/{analysis_id}/findings/{f0['finding_id']}/review",
        json={"action": "mark_uncertain", "notes": "Mark finding uncertain for evaluation test"},
    )

    eval_res = client.get(f"/analyses/{analysis_id}/false-alarm-evaluation")
    assert eval_res.status_code == 200
    eval_data = eval_res.json()

    assert eval_data["uncertain_detections"] >= 1
    assert eval_data["excluded_uncertain_frames"] > 0
    assert eval_data["false_alarms"] == 0

    post_eval_res = client.post(f"/analyses/{analysis_id}/evaluate")
    assert post_eval_res.status_code == 200
    assert post_eval_res.json()["uncertain_detections"] == eval_data["uncertain_detections"]


def test_api_ground_truth_export_splits(api_client):
    client, _ = api_client
    dev_bytes = io.BytesIO(JITTER_BVH.encode("utf-8"))
    held_bytes = io.BytesIO(CLEAN_BVH.encode("utf-8"))

    dev_up = client.post(
        "/upload",
        files={"file": ("clip_dev_gt.bvh", dev_bytes, "application/octet-stream")},
    )
    dev_asset_id = dev_up.json()["asset_id"]

    held_up = client.post(
        "/upload",
        files={"file": ("clip_heldout_gt.bvh", held_bytes, "application/octet-stream")},
    )
    held_asset_id = held_up.json()["asset_id"]

    client.post(
        "/feedback",
        json={
            "asset_id": dev_asset_id,
            "action": "confirm",
            "joint": "LeftLeg",
            "frame_start": 5,
            "frame_end": 10,
            "anomaly_type": "ROTATION_JITTER",
            "split": "dev",
        },
    )
    client.post(
        "/feedback",
        json={
            "asset_id": held_asset_id,
            "action": "mark_missed",
            "joint": "Hips",
            "frame_start": 1,
            "frame_end": 3,
            "anomaly_type": "ROOT_DISCONTINUITY",
            "split": "held-out",
        },
    )

    all_export = client.get("/ground-truth/export")
    assert all_export.status_code == 200
    all_data = all_export.json()
    assert all_data["manifest_version"] == "1.0.0"
    assert "clip_dev_gt.bvh" in all_data["clips"]
    assert "clip_heldout_gt.bvh" in all_data["clips"]

    dev_export = client.get("/ground-truth/export?split=dev")
    assert dev_export.status_code == 200
    dev_data = dev_export.json()
    assert "clip_dev_gt.bvh" in dev_data["clips"]
    assert "clip_heldout_gt.bvh" not in dev_data["clips"]

    held_export = client.get("/ground-truth/export?split=held-out")
    assert held_export.status_code == 200
    held_data = held_export.json()
    assert "clip_heldout_gt.bvh" in held_data["clips"]
    assert "clip_dev_gt.bvh" not in held_data["clips"]




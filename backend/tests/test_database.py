import os
import sqlite3
import tempfile
import pytest

from database import (
    init_db,
    get_db,
    insert_asset,
    get_asset,
    insert_analysis,
    get_analysis,
    insert_workflow_session,
    get_workflow_session,
    update_session_state,
    insert_repair_plan,
    get_repair_plan,
    approve_plan_transaction,
    reject_plan_transaction,
    get_approval,
    invalidate_stale_approvals_for_asset,
    insert_human_feedback,
    get_human_feedback,
    list_human_feedback,
    delete_human_feedback,
    export_ground_truth_splits,
    evaluate_false_alarms,
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
    BVHMetadata,
    AssessmentVerdict,
    CoverageRecord,
    CoverageStatus,
    Evidence,
    BodyPart,
    ReviewAction,
    DatasetSplit,
    HumanFeedback,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_asset_and_foreign_keys(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig123",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=10,
        frame_time=0.033333,
        duration_seconds=0.33333,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-1",
        filename="test.bvh",
        file_path="/tmp/test.bvh",
        file_size_bytes=1024,
        content_hash="hash123",
        skeleton_signature="sig123",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        retrieved = get_asset(conn, "asset-1")
        assert retrieved is not None
        assert retrieved.asset_id == "asset-1"
        assert retrieved.metadata.root_name == "Hips"

    with get_db(temp_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO analyses (
                    analysis_id, asset_id, content_hash, skeleton_signature, parser_version,
                    detector_version, analysis_hash, status, up_axis, created_at
                ) VALUES ('a-bad', 'nonexistent-asset', 'ch', 'ss', '1.0', '1.0', 'ah', 'CLEAN', 'Y', 'now');
                """
            )


def test_atomic_approval_transaction(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig123",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=10,
        frame_time=0.033333,
        duration_seconds=0.33333,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-1",
        filename="test.bvh",
        file_path="/tmp/test.bvh",
        file_size_bytes=1024,
        content_hash="hash123",
        skeleton_signature="sig123",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="analysis-1",
        asset_id="asset-1",
        content_hash="hash123",
        skeleton_signature="sig123",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash123",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[],
        created_at="2026-09-04T12:00:00Z",
    )
    session = WorkflowSession(
        session_id="session-1",
        asset_id="asset-1",
        analysis_id="analysis-1",
        lifecycle_state=LifecycleState.AWAITING_APPROVAL,
        created_at="2026-09-04T12:00:00Z",
        updated_at="2026-09-04T12:00:00Z",
    )
    plan = RepairPlan(
        plan_id="plan-1",
        session_id="session-1",
        analysis_id="analysis-1",
        analysis_hash="ahash123",
        version=1,
        selected_finding_ids=["f1"],
        proposed_roster=[],
        status="PENDING",
        created_at="2026-09-04T12:00:00Z",
        expires_at="2026-09-04T13:00:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)
        insert_workflow_session(conn, session)
        insert_repair_plan(conn, plan)

        approval = Approval(
            approval_id="appr-1",
            session_id="session-1",
            plan_id="plan-1",
            repair_plan_version=1,
            analysis_hash="ahash123",
            selected_finding_ids=["f1"],
            roster_hash="rosterhash",
            approved_by="authenticated_user",
            approved_at="2026-09-04T12:05:00Z",
            valid_until="2026-09-04T13:00:00Z",
        )

        approve_plan_transaction(conn, approval, "2026-09-04T12:05:00Z")

        saved_appr = get_approval(conn, "appr-1")
        assert saved_appr is not None
        assert saved_appr.approval_id == "appr-1"

        saved_plan = get_repair_plan(conn, "plan-1")
        assert saved_plan.status == "APPROVED"

        saved_session = get_workflow_session(conn, "session-1")
        assert saved_session.lifecycle_state == LifecycleState.APPROVED
        assert saved_session.approval_id == "appr-1"


def test_atomic_rejection_transaction(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig123",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=10,
        frame_time=0.033333,
        duration_seconds=0.33333,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-2",
        filename="test2.bvh",
        file_path="/tmp/test2.bvh",
        file_size_bytes=1024,
        content_hash="hash456",
        skeleton_signature="sig456",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )
    analysis = Analysis(
        analysis_id="analysis-2",
        asset_id="asset-2",
        content_hash="hash456",
        skeleton_signature="sig456",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash456",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[],
        created_at="2026-09-04T12:00:00Z",
    )
    session = WorkflowSession(
        session_id="session-2",
        asset_id="asset-2",
        analysis_id="analysis-2",
        lifecycle_state=LifecycleState.AWAITING_APPROVAL,
        created_at="2026-09-04T12:00:00Z",
        updated_at="2026-09-04T12:00:00Z",
    )
    plan = RepairPlan(
        plan_id="plan-2",
        session_id="session-2",
        analysis_id="analysis-2",
        analysis_hash="ahash456",
        version=1,
        selected_finding_ids=["f2"],
        proposed_roster=[],
        status="PENDING",
        created_at="2026-09-04T12:00:00Z",
        expires_at="2026-09-04T13:00:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)
        insert_workflow_session(conn, session)
        insert_repair_plan(conn, plan)

        reject_plan_transaction(conn, "session-2", "plan-2", "2026-09-04T12:06:00Z")

        saved_plan = get_repair_plan(conn, "plan-2")
        assert saved_plan.status == "REJECTED"

        saved_session = get_workflow_session(conn, "session-2")
        assert saved_session.lifecycle_state == LifecycleState.REVIEWING_FINDINGS


def test_analysis_detector_status_persistence(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig999",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=10,
        frame_time=0.033333,
        duration_seconds=0.33333,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-status-test",
        filename="status.bvh",
        file_path="/tmp/status.bvh",
        file_size_bytes=1024,
        content_hash="hash999",
        skeleton_signature="sig999",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )
    expected_status = {
        "rotation_jitter": "COMPLETED",
        "translation_jitter": "INCONCLUSIVE",
        "root_discontinuity": "INCONCLUSIVE",
        "foot_contact": "INCONCLUSIVE",
    }
    analysis = Analysis(
        analysis_id="analysis-status-test",
        asset_id="asset-status-test",
        content_hash="hash999",
        skeleton_signature="sig999",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash999",
        status=AnalysisStatus.INCONCLUSIVE,
        up_axis="Z",
        findings=[],
        detector_status=expected_status,
        created_at="2026-09-04T12:00:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)
        retrieved = get_analysis(conn, "analysis-status-test")
        assert retrieved is not None
        assert retrieved.detector_status == expected_status
        assert retrieved.up_axis == "Z"


def test_primary_key_uniqueness_enforcement(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig_uniq",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=10,
        frame_time=0.033333,
        duration_seconds=0.33333,
        skeleton_scale=100.0,
    )
    asset1 = Asset(
        asset_id="dup-id",
        filename="test1.bvh",
        file_path="/tmp/test1.bvh",
        file_size_bytes=100,
        content_hash="chash1",
        skeleton_signature="sig_uniq",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )
    asset2 = Asset(
        asset_id="dup-id",
        filename="test2.bvh",
        file_path="/tmp/test2.bvh",
        file_size_bytes=200,
        content_hash="chash2",
        skeleton_signature="sig_uniq",
        metadata=meta,
        created_at="2026-09-04T12:00:00Z",
    )
    with get_db(temp_db) as conn:
        insert_asset(conn, asset1)
        with pytest.raises(sqlite3.IntegrityError):
            insert_asset(conn, asset2)


def test_verdicts_coverage_records_and_evidence_persistence(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig-persist",
        root_name="Hips",
        joints=["Hips", "LeftFoot"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"], "LeftFoot": ["Zrotation", "Xrotation", "Yrotation"]},
        total_channels=6,
        frame_count=20,
        frame_time=0.033333,
        duration_seconds=0.66666,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-persist-1",
        filename="persist.bvh",
        file_path="/tmp/persist.bvh",
        file_size_bytes=1024,
        content_hash="hash-persist-1",
        skeleton_signature="sig-persist",
        metadata=meta,
        created_at="2026-09-09T10:00:00Z",
    )
    evidence = Evidence(
        metric_name="sliding_velocity",
        measured_value=12.5,
        threshold=5.0,
        unit="cm/s",
        peak_frame=10,
        details={"peak_speed": 12.5, "duration_frames": 10},
    )
    verdict = AssessmentVerdict.LIKELY_VISIBLE_DEFECT
    finding = Finding(
        finding_id="finding-persist-1",
        analysis_id="analysis-persist-1",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=5,
        frame_end=15,
        time_start=5 * 0.033333,
        time_end=15 * 0.033333,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.88,
        verdict=verdict,
        evidence=evidence,
        explanation="Foot sliding detected across frames 5-15",
    )
    coverage = CoverageRecord(
        check_name="foot_contact",
        status=CoverageStatus.COVERED,
        covered=True,
        prerequisites_met=True,
        evaluated_joints=["LeftFoot"],
        evaluated_frames=20,
        reason=None,
    )
    analysis = Analysis(
        analysis_id="analysis-persist-1",
        asset_id="asset-persist-1",
        content_hash="hash-persist-1",
        skeleton_signature="sig-persist",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash-persist-1",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[finding],
        detector_status={"foot_contact": "COMPLETED"},
        coverage_records=[coverage],
        created_at="2026-09-09T10:00:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)
        retrieved = get_analysis(conn, "analysis-persist-1")

        assert retrieved is not None
        assert len(retrieved.coverage_records) == 1
        rec = retrieved.coverage_records[0]
        assert isinstance(rec, CoverageRecord)
        assert rec.check_name == "foot_contact"
        assert rec.status == CoverageStatus.COVERED
        assert rec.covered is True
        assert rec.evaluated_joints == ["LeftFoot"]
        assert rec.evaluated_frames == 20

        assert len(retrieved.findings) == 1
        f = retrieved.findings[0]
        assert f.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT
        assert f.verdict.value == "Likely visible defect"

        assert isinstance(f.evidence, Evidence)
        assert f.evidence.metric_name == "sliding_velocity"
        assert f.evidence.measured_value == 12.5
        assert f.evidence.threshold == 5.0
        assert f.evidence.unit == "cm/s"
        assert f.evidence.peak_frame == 10
        assert f.evidence.display_peak_frame == 11
        assert f.evidence.playback_frame_start == 0
        assert f.evidence.playback_frame_end == 25
        assert f.evidence.details["peak_speed"] == 12.5


def test_invalidate_stale_approvals_when_asset_reanalyzed(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig-stale",
        root_name="Hips",
        joints=["Hips"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=10,
        frame_time=0.033333,
        duration_seconds=0.33333,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-stale-1",
        filename="stale.bvh",
        file_path="/tmp/stale.bvh",
        file_size_bytes=512,
        content_hash="hash-stale-1",
        skeleton_signature="sig-stale",
        metadata=meta,
        created_at="2026-09-09T10:00:00Z",
    )
    analysis1 = Analysis(
        analysis_id="analysis-stale-1",
        asset_id="asset-stale-1",
        content_hash="hash-stale-1",
        skeleton_signature="sig-stale",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash-stale-1",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[],
        detector_status={},
        coverage_records=[],
        created_at="2026-09-09T10:00:00Z",
    )
    session = WorkflowSession(
        session_id="session-stale-1",
        asset_id="asset-stale-1",
        analysis_id="analysis-stale-1",
        lifecycle_state=LifecycleState.REVIEWING_FINDINGS,
        created_at="2026-09-09T10:00:00Z",
        updated_at="2026-09-09T10:00:00Z",
    )
    plan = RepairPlan(
        plan_id="plan-stale-1",
        session_id="session-stale-1",
        analysis_id="analysis-stale-1",
        analysis_hash="ahash-stale-1",
        version=1,
        selected_finding_ids=[],
        proposed_roster=[],
        status="PENDING",
        created_at="2026-09-09T10:01:00Z",
        expires_at="2026-09-09T11:01:00Z",
    )
    approval = Approval(
        approval_id="approval-stale-1",
        session_id="session-stale-1",
        plan_id="plan-stale-1",
        repair_plan_version=1,
        analysis_hash="ahash-stale-1",
        selected_finding_ids=[],
        roster_hash="rhash-stale-1",
        approved_by="user",
        approved_at="2026-09-09T10:02:00Z",
        valid_until="2026-09-09T11:02:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis1)
        insert_workflow_session(conn, session)
        insert_repair_plan(conn, plan)
        approve_plan_transaction(conn, approval, "2026-09-09T10:02:00Z")

        approved_sess = get_workflow_session(conn, "session-stale-1")
        assert approved_sess.lifecycle_state == LifecycleState.APPROVED
        assert approved_sess.approval_id == "approval-stale-1"
        assert approved_sess.plan_id == "plan-stale-1"

        analysis2 = Analysis(
            analysis_id="analysis-stale-2",
            asset_id="asset-stale-1",
            content_hash="hash-stale-1",
            skeleton_signature="sig-stale",
            parser_version="1.0.0",
            detector_version="1.0.0",
            analysis_hash="ahash-stale-2",
            status=AnalysisStatus.CLEAN,
            up_axis="Y",
            findings=[],
            detector_status={},
            coverage_records=[],
            created_at="2026-09-09T10:05:00Z",
        )
        insert_analysis(conn, analysis2)

        reset_sess = get_workflow_session(conn, "session-stale-1")
        assert reset_sess.lifecycle_state == LifecycleState.REVIEWING_FINDINGS
        assert reset_sess.approval_id is None
        assert reset_sess.plan_id is None

        superseded_plan = get_repair_plan(conn, "plan-stale-1")
        assert superseded_plan.status == "SUPERSEDED"

        stored_approval = get_approval(conn, "approval-stale-1")
        assert stored_approval is not None
        assert stored_approval.approval_id == "approval-stale-1"


def test_human_feedback_persistence_and_crud(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig-fb",
        root_name="Hips",
        joints=["Hips", "LeftFoot"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"], "LeftFoot": ["Zrotation", "Xrotation", "Yrotation"]},
        total_channels=6,
        frame_count=50,
        frame_time=0.033333,
        duration_seconds=1.6666,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-fb-1",
        filename="feedback_test.bvh",
        file_path="/tmp/feedback_test.bvh",
        file_size_bytes=1024,
        content_hash="hash-fb-1",
        skeleton_signature="sig-fb",
        metadata=meta,
        created_at="2026-09-09T10:00:00Z",
    )
    with get_db(temp_db) as conn:
        insert_asset(conn, asset)

        fb1 = HumanFeedback(
            feedback_id="fb-1",
            asset_id="asset-fb-1",
            action=ReviewAction.CONFIRM,
            joint="LeftFoot",
            frame_start=10,
            frame_end=20,
            anomaly_type="PLANTED_FOOT_SLIDING",
            notes="Confirmed foot sliding defect",
            split="dev",
            created_at="2026-09-09T10:01:00Z",
            updated_at="2026-09-09T10:01:00Z",
        )
        fb2 = HumanFeedback(
            feedback_id="fb-2",
            asset_id="asset-fb-1",
            action=ReviewAction.REJECT,
            joint="Hips",
            frame_start=5,
            frame_end=15,
            notes="Rejected normal root movement",
            split="dev",
            created_at="2026-09-09T10:02:00Z",
            updated_at="2026-09-09T10:02:00Z",
        )
        fb3 = HumanFeedback(
            feedback_id="fb-3",
            asset_id="asset-fb-1",
            action=ReviewAction.MARK_MISSED,
            joint="LeftFoot",
            frame_start=30,
            frame_end=35,
            anomaly_type="PLANTED_FOOT_SLIDING",
            notes="Detector missed sliding during pivot",
            split="dev",
            created_at="2026-09-09T10:03:00Z",
            updated_at="2026-09-09T10:03:00Z",
        )
        fb4 = HumanFeedback(
            feedback_id="fb-4",
            asset_id="asset-fb-1",
            action=ReviewAction.MARK_UNCERTAIN,
            joint="Hips",
            frame_start=25,
            frame_end=28,
            notes="Ambiguous transition",
            split="dev",
            created_at="2026-09-09T10:04:00Z",
            updated_at="2026-09-09T10:04:00Z",
        )

        insert_human_feedback(conn, fb1)
        insert_human_feedback(conn, fb2)
        insert_human_feedback(conn, fb3)
        insert_human_feedback(conn, fb4)

        retrieved1 = get_human_feedback(conn, "fb-1")
        assert retrieved1 is not None
        assert retrieved1.action == ReviewAction.CONFIRM
        assert retrieved1.joint == "LeftFoot"
        assert retrieved1.frame_start == 10
        assert retrieved1.frame_end == 20
        assert retrieved1.anomaly_type == "PLANTED_FOOT_SLIDING"

        all_fb = list_human_feedback(conn, asset_id="asset-fb-1")
        assert len(all_fb) == 4

        confirms = list_human_feedback(conn, asset_id="asset-fb-1", action="confirm")
        assert len(confirms) == 1
        assert confirms[0].feedback_id == "fb-1"

        uncertains = list_human_feedback(conn, asset_id="asset-fb-1", action="mark_uncertain")
        assert len(uncertains) == 1
        assert uncertains[0].feedback_id == "fb-4"

        del_ok = delete_human_feedback(conn, "fb-2")
        assert del_ok is True
        assert get_human_feedback(conn, "fb-2") is None
        assert len(list_human_feedback(conn, asset_id="asset-fb-1")) == 3


def test_false_alarm_evaluation_excludes_uncertain_intervals(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig-fa",
        root_name="Hips",
        joints=["Hips", "LeftFoot", "RightArm"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=100,
        frame_time=0.033333,
        duration_seconds=3.3333,
        skeleton_scale=100.0,
    )
    asset = Asset(
        asset_id="asset-fa-1",
        filename="eval_test.bvh",
        file_path="/tmp/eval_test.bvh",
        file_size_bytes=2048,
        content_hash="hash-fa-1",
        skeleton_signature="sig-fa",
        metadata=meta,
        created_at="2026-09-09T10:00:00Z",
    )
    f_confirmed = Finding(
        finding_id="f-conf",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=10,
        frame_end=15,
        time_start=0.33,
        time_end=0.50,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.9,
        explanation="Left foot skate detected",
        verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
    )
    f_rejected = Finding(
        finding_id="f-rej",
        affected_joint="RightArm",
        affected_body_part=BodyPart.ARM,
        frame_start=20,
        frame_end=25,
        time_start=0.66,
        time_end=0.83,
        anomaly_type=AnomalyType.ROTATION_JITTER,
        severity=Severity.MEDIUM,
        confidence=0.7,
        explanation="Right arm pop detected",
        verdict=AssessmentVerdict.REVIEW,
    )
    f_uncertain = Finding(
        finding_id="f-unc",
        affected_joint="Hips",
        affected_body_part=BodyPart.PELVIS,
        frame_start=30,
        frame_end=35,
        time_start=1.0,
        time_end=1.16,
        anomaly_type=AnomalyType.TRANSLATION_JITTER,
        severity=Severity.MEDIUM,
        confidence=0.65,
        explanation="Ambiguous root trajectory",
        verdict=AssessmentVerdict.REVIEW,
    )
    analysis = Analysis(
        analysis_id="analysis-fa-1",
        asset_id="asset-fa-1",
        content_hash="hash-fa-1",
        skeleton_signature="sig-fa",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash-fa-1",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[f_confirmed, f_rejected, f_uncertain],
        detector_status={},
        coverage_records=[],
        created_at="2026-09-09T10:00:00Z",
    )

    with get_db(temp_db) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)

        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-conf",
                asset_id="asset-fa-1",
                finding_id="f-conf",
                action=ReviewAction.CONFIRM,
                joint="LeftFoot",
                frame_start=10,
                frame_end=15,
                anomaly_type="PLANTED_FOOT_SLIDING",
                split="dev",
                created_at="2026-09-09T10:05:00Z",
                updated_at="2026-09-09T10:05:00Z",
            ),
        )
        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-rej",
                asset_id="asset-fa-1",
                finding_id="f-rej",
                action=ReviewAction.REJECT,
                joint="RightArm",
                frame_start=20,
                frame_end=25,
                split="dev",
                created_at="2026-09-09T10:05:00Z",
                updated_at="2026-09-09T10:05:00Z",
            ),
        )
        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-unc",
                asset_id="asset-fa-1",
                finding_id="f-unc",
                action=ReviewAction.MARK_UNCERTAIN,
                joint="Hips",
                frame_start=30,
                frame_end=35,
                split="dev",
                created_at="2026-09-09T10:05:00Z",
                updated_at="2026-09-09T10:05:00Z",
            ),
        )
        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-miss",
                asset_id="asset-fa-1",
                action=ReviewAction.MARK_MISSED,
                joint="LeftFoot",
                frame_start=50,
                frame_end=55,
                anomaly_type="PLANTED_FOOT_SLIDING",
                split="dev",
                created_at="2026-09-09T10:05:00Z",
                updated_at="2026-09-09T10:05:00Z",
            ),
        )

        res = evaluate_false_alarms(conn, "asset-fa-1", "analysis-fa-1")
        assert res["total_detections"] == 3
        assert res["confirmed_detections"] == 1
        assert res["rejected_detections"] == 1
        assert res["uncertain_detections"] == 1
        assert res["missed_detections"] == 1
        assert res["false_alarms"] == 1
        assert res["excluded_uncertain_frames"] == 6
        assert res["precision"] == 0.5
        assert res["recall"] == 0.5


def test_export_annotated_ground_truth_splits(temp_db):
    meta = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature="sig-split",
        root_name="Hips",
        joints=["Hips", "RightArm"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=80,
        frame_time=0.033333,
        duration_seconds=2.6666,
        skeleton_scale=100.0,
    )
    asset_dev = Asset(
        asset_id="asset-dev-1",
        filename="clip_dev.bvh",
        file_path="/tmp/clip_dev.bvh",
        file_size_bytes=1000,
        content_hash="hash-dev-1",
        skeleton_signature="sig-split",
        metadata=meta,
        created_at="2026-09-09T10:00:00Z",
    )
    asset_heldout = Asset(
        asset_id="asset-heldout-1",
        filename="clip_heldout.bvh",
        file_path="/tmp/clip_heldout.bvh",
        file_size_bytes=1000,
        content_hash="hash-heldout-1",
        skeleton_signature="sig-split",
        metadata=meta,
        created_at="2026-09-09T10:00:00Z",
    )
    with get_db(temp_db) as conn:
        insert_asset(conn, asset_dev)
        insert_asset(conn, asset_heldout)

        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-dev-1",
                asset_id="asset-dev-1",
                action=ReviewAction.CONFIRM,
                joint="Hips",
                frame_start=10,
                frame_end=15,
                anomaly_type="ROOT_DISCONTINUITY",
                split="dev",
                created_at="2026-09-09T10:01:00Z",
                updated_at="2026-09-09T10:01:00Z",
            ),
        )
        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-dev-2",
                asset_id="asset-dev-1",
                action=ReviewAction.MARK_UNCERTAIN,
                joint="RightArm",
                frame_start=20,
                frame_end=25,
                split="dev",
                created_at="2026-09-09T10:01:00Z",
                updated_at="2026-09-09T10:01:00Z",
            ),
        )

        insert_human_feedback(
            conn,
            HumanFeedback(
                feedback_id="fb-ho-1",
                asset_id="asset-heldout-1",
                action=ReviewAction.MARK_MISSED,
                joint="RightArm",
                frame_start=30,
                frame_end=40,
                anomaly_type="ROTATION_JITTER",
                split="held-out",
                created_at="2026-09-09T10:02:00Z",
                updated_at="2026-09-09T10:02:00Z",
            ),
        )

        dev_export = export_ground_truth_splits(conn, split_filter="dev")
        assert "clip_dev.bvh" in dev_export["clips"]
        assert "clip_heldout.bvh" not in dev_export["clips"]
        dev_clip = dev_export["clips"]["clip_dev.bvh"]
        assert len(dev_clip["confirmed_defective"]) == 1
        assert "RightArm" in dev_clip["transition_uncertain"]

        ho_export = export_ground_truth_splits(conn, split_filter="held-out")
        assert "clip_heldout.bvh" in ho_export["clips"]
        assert "clip_dev.bvh" not in ho_export["clips"]
        ho_clip = ho_export["clips"]["clip_heldout.bvh"]
        assert len(ho_clip["confirmed_defective"]) == 1
        assert ho_clip["confirmed_defective"][0]["anomaly_type"] == "ROTATION_JITTER"



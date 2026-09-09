import os
import json
import sqlite3
import tempfile
import pytest
from models import (
    AssessmentVerdict,
    CoverageStatus,
    CoveragePrerequisites,
    CoverageRecord,
    Evidence,
    Finding,
    Analysis,
    AnalysisStatus,
    AnomalyType,
    Severity,
    BodyPart,
)
from database import init_db, get_db, insert_analysis, get_analysis, insert_asset, Asset, BVHMetadata


def test_assessment_verdict_enum_values():
    assert AssessmentVerdict.LIKELY_VISIBLE_DEFECT.value == "Likely visible defect"
    assert AssessmentVerdict.REVIEW.value == "Review"
    assert AssessmentVerdict.NUMERICAL_ONLY.value == "Numerical-only"
    assert AssessmentVerdict.INCONCLUSIVE.value == "Inconclusive"

    verdicts = [v.value for v in AssessmentVerdict]
    assert "Likely visible defect" in verdicts
    assert "Review" in verdicts
    assert "Numerical-only" in verdicts
    assert "Inconclusive" in verdicts


def test_evidence_model_and_frame_conventions():
    ev = Evidence(
        metric_name="angular_accel",
        measured_value=24500.0,
        threshold=20000.0,
        unit="deg_per_sec2",
        peak_frame=42,
        context_padding_frames=15,
    )

    assert ev.peak_frame == 42
    assert ev.display_peak_frame == 43
    assert ev.playback_frame_start == 27
    assert ev.playback_frame_end == 57
    assert ev.display_playback_frame_start == 28
    assert ev.display_playback_frame_end == 58

    assert ev["peak_frame"] == 42
    assert "measured_value" in ev
    assert ev.get("threshold") == 20000.0

    ev["custom_metric"] = 999.0
    assert ev["custom_metric"] == 999.0
    assert ev.to_dict()["custom_metric"] == 999.0


def test_finding_frame_conventions_and_playback_padding():
    finding = Finding(
        finding_id="f_sample_01",
        affected_joint="RightUpLeg",
        affected_body_part=BodyPart.LEG,
        frame_start=10,
        frame_end=20,
        time_start=0.333,
        time_end=0.666,
        anomaly_type=AnomalyType.ROM_HYPEREXTENSION,
        severity=Severity.HIGH,
        confidence=0.92,
        evidence={"metric_name": "knee_extension", "peak_frame": 15},
        explanation="Knee hyperextension beyond physiological anatomical limit.",
        context_padding_frames=10,
    )

    assert finding.frame_start == 10
    assert finding.frame_end == 20
    assert finding.display_frame_start == 11
    assert finding.display_frame_end == 21

    assert finding.peak_frame == 15
    assert finding.display_peak_frame == 16

    assert finding.playback_frame_start == 0
    assert finding.playback_frame_end == 30
    assert finding.display_playback_frame_start == 1
    assert finding.display_playback_frame_end == 31

    bounds_internal = finding.get_playback_bounds(total_frames=25)
    assert bounds_internal == (0, 24)

    bounds_display = finding.get_display_playback_bounds(total_frames=25)
    assert bounds_display == (1, 25)


def test_finding_verdict_inference_and_explicit_assignment():
    high_finding = Finding(
        finding_id="f_high",
        affected_joint="Hips",
        affected_body_part=BodyPart.PELVIS,
        frame_start=5,
        frame_end=8,
        time_start=0.1,
        time_end=0.2,
        anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
        severity=Severity.HIGH,
        confidence=0.95,
        evidence={},
        explanation="High speed root discontinuity jump.",
    )
    assert high_finding.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT

    low_finding = Finding(
        finding_id="f_low",
        affected_joint="Spine",
        affected_body_part=BodyPart.SPINE,
        frame_start=10,
        frame_end=15,
        time_start=0.3,
        time_end=0.5,
        anomaly_type=AnomalyType.ROTATION_JITTER,
        severity=Severity.LOW,
        confidence=0.45,
        evidence={},
        explanation="Subtle rotational velocity fluctuation.",
    )
    assert low_finding.verdict == AssessmentVerdict.NUMERICAL_ONLY

    explicit_finding = Finding(
        finding_id="f_exp",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=20,
        frame_end=30,
        time_start=0.6,
        time_end=1.0,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.MEDIUM,
        confidence=0.75,
        evidence={},
        explanation="Potential foot slide under review.",
        verdict=AssessmentVerdict.REVIEW,
    )
    assert explicit_finding.verdict == AssessmentVerdict.REVIEW


def test_evidence_interoperability_in_finding():
    model_ev = Evidence(
        metric_name="tangential_velocity",
        measured_value=12.4,
        threshold=4.5,
        unit="units_per_sec",
        peak_frame=18,
    )

    finding_with_model = Finding(
        finding_id="f_model_ev",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=15,
        frame_end=25,
        time_start=0.5,
        time_end=0.8,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.90,
        evidence=model_ev,
        explanation="Planted foot horizontal translation exceeding threshold.",
    )

    assert finding_with_model.peak_frame == 18
    assert finding_with_model.display_peak_frame == 19
    assert finding_with_model.get_evidence_model().measured_value == 12.4


def test_coverage_record_decoupled_from_findings():
    scale_missing_prereqs = CoveragePrerequisites(scale=False)
    coverage_no_scale = CoverageRecord(
        check_name="PLANTED_FOOT_SLIDING",
        prerequisites=scale_missing_prereqs,
        reason="Skeleton rest-pose scale height is non-positive or indeterminate",
    )
    assert not coverage_no_scale.covered
    assert not coverage_no_scale.prerequisites_met
    assert "scale" in coverage_no_scale.missing_prerequisites
    assert coverage_no_scale.status == CoverageStatus.NOT_COVERED

    foot_missing_prereqs = CoveragePrerequisites(joint_presence=False)
    coverage_no_foot = CoverageRecord(
        check_name="PLANTED_FOOT_SLIDING",
        prerequisites=foot_missing_prereqs,
        reason="No joints identified matching foot anatomical nomenclature",
    )
    assert not coverage_no_foot.covered
    assert "joint_presence" in coverage_no_foot.missing_prerequisites

    full_prereqs = CoveragePrerequisites(
        scale=True,
        up_axis=True,
        joint_presence=True,
        frame_count=True,
        channels=True,
    )
    coverage_clean = CoverageRecord(
        check_name="ROM_HYPEREXTENSION",
        prerequisites=full_prereqs,
        evaluated_joints=["RightUpLeg", "RightLeg", "LeftUpLeg", "LeftLeg"],
        evaluated_frames=120,
    )
    assert coverage_clean.covered
    assert coverage_clean.prerequisites_met
    assert coverage_clean.status == CoverageStatus.COVERED
    assert len(coverage_clean.evaluated_joints) == 4
    assert coverage_clean.evaluated_frames == 120


def test_analysis_coverage_record_helpers():
    analysis = Analysis(
        analysis_id="test_cov_analysis",
        asset_id="test_asset",
        content_hash="chash_test",
        skeleton_signature="ssig_test",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="ahash_test",
        status=AnalysisStatus.CLEAN,
        up_axis="Y",
        created_at="2026-09-09T00:00:00Z",
    )

    rec = CoverageRecord(
        check_name="ROOT_DISCONTINUITY",
        status=CoverageStatus.COVERED,
        covered=True,
        evaluated_joints=["Hips"],
        evaluated_frames=100,
    )
    analysis.add_coverage_record(rec)

    queried = analysis.get_coverage("ROOT_DISCONTINUITY")
    assert queried is not None
    assert queried.covered is True
    assert analysis.detector_status["ROOT_DISCONTINUITY"] == "COVERED"
    assert analysis.get_coverage("NON_EXISTENT") is None


def test_database_persistence_with_evidence_and_finding_contracts():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    metadata = BVHMetadata(
        skeleton_signature="test_sig",
        root_name="Hips",
        joints=["Hips", "Spine"],
        channel_order={"Hips": ["Xposition", "Yposition", "Zposition"]},
        total_channels=3,
        frame_count=50,
        frame_time=0.033333,
        duration_seconds=1.666,
        skeleton_scale=170.0,
    )

    asset = Asset(
        asset_id="asset_persist_test",
        filename="test.bvh",
        file_path="/tmp/test.bvh",
        file_size_bytes=1024,
        content_hash="content_hash_123",
        skeleton_signature="test_sig",
        metadata=metadata,
        created_at="2026-09-09T00:00:00Z",
    )

    structured_ev = Evidence(
        metric_name="linear_displacement_speed",
        measured_value=320.5,
        threshold=100.0,
        unit="units_per_sec",
        peak_frame=12,
    )

    finding = Finding(
        finding_id="finding_persist_test",
        analysis_id="analysis_persist_test",
        affected_joint="Hips",
        affected_body_part=BodyPart.PELVIS,
        frame_start=10,
        frame_end=15,
        time_start=0.333,
        time_end=0.5,
        anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
        severity=Severity.CRITICAL,
        confidence=0.98,
        evidence=structured_ev,
        explanation="Severe root translation teleportation.",
    )

    analysis = Analysis(
        analysis_id="analysis_persist_test",
        asset_id="asset_persist_test",
        content_hash="content_hash_123",
        skeleton_signature="test_sig",
        parser_version="1.0.0",
        detector_version="1.0.0",
        analysis_hash="analysis_hash_123",
        status=AnalysisStatus.FINDINGS,
        up_axis="Y",
        findings=[finding],
        created_at="2026-09-09T00:00:00Z",
    )

    with get_db(db_path) as conn:
        insert_asset(conn, asset)
        insert_analysis(conn, analysis)
        retrieved = get_analysis(conn, "analysis_persist_test")

    assert retrieved is not None
    assert len(retrieved.findings) == 1
    retrieved_f = retrieved.findings[0]
    assert retrieved_f.finding_id == "finding_persist_test"
    assert retrieved_f.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT
    assert retrieved_f.display_frame_start == 11
    assert retrieved_f.display_frame_end == 16
    assert retrieved_f.peak_frame == 12
    assert retrieved_f.display_peak_frame == 13
    assert retrieved_f.playback_frame_start == 0
    assert retrieved_f.playback_frame_end == 30

    if os.path.exists(db_path):
        os.remove(db_path)

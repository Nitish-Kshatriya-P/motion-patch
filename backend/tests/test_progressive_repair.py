import os
os.environ["TESTING"] = "1"
import tempfile
import pytest

from bvh_parser import parse_bvh_file
from models import Finding, AnomalyType, Severity, BodyPart, AgentSpecification
from agent import (
    build_finding_task_context,
    generate_agent_task_prompt,
    validate_candidate_authorized_changes,
    execute_progressive_finding_repair,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "01_WalkFwd_Loop_RightContactDropout.bvh")

def test_validate_candidate_authorized_changes():
    base_motion = [[0.0, 10.0, 20.0], [0.0, 10.0, 20.0]]
    authorized_mask = {(0, 1), (1, 1)}

    ok, err = validate_candidate_authorized_changes({}, authorized_mask, base_motion)
    assert not ok
    assert "no channel modifications" in err

    ok, err = validate_candidate_authorized_changes({(0, 2): 20.0}, authorized_mask, base_motion)
    assert not ok
    assert "unauthorized" in err

    ok, err = validate_candidate_authorized_changes({(0, 1): 10.0, (1, 1): 10.0}, authorized_mask, base_motion)
    assert not ok
    assert "identical" in err

    ok, err = validate_candidate_authorized_changes({(0, 1): 12.5, (1, 1): 10.0}, authorized_mask, base_motion)
    assert ok
    assert err == ""

def test_build_finding_task_context():
    if not os.path.exists(FIXTURE_PATH):
        pytest.skip("Fixture not found")
    parsed = parse_bvh_file(FIXTURE_PATH)
    finding = {
        "finding_id": "f-test-1",
        "affected_joint": "RightFoot",
        "frame_start": 20,
        "frame_end": 28,
        "anomaly_type": "PLANTED_FOOT_SLIDING",
        "evidence": {"drift": 5.2},
        "explanation": "Foot slides during stance",
    }
    ctx = build_finding_task_context(finding, parsed, retry_feedback="Reduce horizontal velocity")
    assert ctx["joint"] == "RightFoot"
    assert ctx["frame_start"] == 20
    assert ctx["frame_end"] == 28
    assert ctx["retry_feedback"] == "Reduce horizontal velocity"
    assert len(ctx["channels"]) > 0

def test_generate_agent_task_prompt():
    prompt = generate_agent_task_prompt(
        role="Foot Grounding Specialist",
        target_bones=["RightFoot"],
        target_frames=[21, 28],
        findings=[{
            "anomaly_type": "PLANTED_FOOT_SLIDING",
            "affected_joint": "RightFoot",
            "frame_start": 21,
            "frame_end": 28,
            "evidence": {"speed": 4.1},
            "explanation": "Foot drifts along ground plane",
        }],
        feedback="Previous attempt changed no values",
    )
    assert "Foot Grounding Specialist" in prompt
    assert "RightFoot" in prompt
    assert "PLANTED_FOOT_SLIDING" in prompt
    assert "Previous attempt feedback (MUST FIX):" in prompt

def test_execute_progressive_finding_repair_completed(tmp_path):
    if not os.path.exists(FIXTURE_PATH):
        pytest.skip("Fixture not found")
    out_bvh = str(tmp_path / "progressive_fixed.bvh")
    findings = [
        Finding(
            finding_id="f1",
            affected_joint="RightFoot",
            affected_body_part=BodyPart.FOOT,
            frame_start=21,
            frame_end=28,
            time_start=0.35,
            time_end=0.46,
            anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
            severity=Severity.HIGH,
            confidence=0.95,
            evidence={"frames": [21, 28]},
            explanation="Foot contact dropout",
            created_at="2026-09-10T00:00:00Z",
        ),
    ]
    rep_path, metrics = execute_progressive_finding_repair(
        input_bvh_path=FIXTURE_PATH,
        output_bvh_path=out_bvh,
        approved_findings=findings,
        max_retries=3,
    )
    assert rep_path is not None
    assert metrics["outcome_status"] == "COMPLETED"
    assert metrics["qa_passed"] is True
    assert metrics["fixed_count"] == 1
    assert metrics["unresolved_count"] == 0
    assert len(metrics["fixed_findings"]) == 1
    assert "repaired successfully" in metrics["summary_message"]
    assert os.path.exists(out_bvh)

def test_execute_progressive_finding_repair_partial_or_failure(tmp_path):
    if not os.path.exists(FIXTURE_PATH):
        pytest.skip("Fixture not found")
    out_bvh = str(tmp_path / "progressive_partial.bvh")
    findings = [
        Finding(
            finding_id="f-good",
            affected_joint="RightFoot",
            affected_body_part=BodyPart.FOOT,
            frame_start=21,
            frame_end=28,
            time_start=0.35,
            time_end=0.46,
            anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
            severity=Severity.HIGH,
            confidence=0.95,
            evidence={"frames": [21, 28]},
            explanation="Foot contact dropout",
            created_at="2026-09-10T00:00:00Z",
        ),
        Finding(
            finding_id="f-unresolvable",
            affected_joint="Head",
            affected_body_part=BodyPart.HEAD,
            frame_start=5,
            frame_end=15,
            time_start=0.08,
            time_end=0.25,
            anomaly_type=AnomalyType.ROTATION_JITTER,
            severity=Severity.LOW,
            confidence=0.6,
            evidence={},
            explanation="Subtle micro jitter",
            created_at="2026-09-10T00:00:00Z",
        ),
    ]
    rep_path, metrics = execute_progressive_finding_repair(
        input_bvh_path=FIXTURE_PATH,
        output_bvh_path=out_bvh,
        approved_findings=findings,
        max_retries=3,
    )
    assert metrics["outcome_status"] in ("COMPLETED", "PARTIALLY_REPAIRED")
    assert metrics["fixed_count"] >= 1
    assert len(metrics["fixed_findings"]) >= 1
    assert metrics["qa_passed"] is True

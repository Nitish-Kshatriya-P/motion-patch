import os
import sys
import math
import tempfile
import shutil
import hashlib
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bvh_parser import parse_bvh_file
from detector import (
    unwrap_angles,
    analyze_bvh,
    compute_analysis_hash,
    compute_roster_hash,
    detect_rotation_jitter,
    detect_root_discontinuity,
    detect_foot_sliding,
    detect_sensor_tracking_artifacts,
    detect_representation_singularities,
    detect_biomechanical_violations,
    detect_contact_and_ground,
    detect_volumetric_self_collisions,
    detect_physical_dynamics,
    detect_motion_pops,
    assess_motion_pop_candidate,
    compute_forward_kinematics,
    DETECTOR_VERSION,
    DefectCandidate,
    generate_pop_jump_candidates,
    generate_repeated_jitter_candidates,
    generate_freeze_candidates,
    generate_foot_sliding_candidates,
    generate_ground_contact_candidates,
    generate_biomechanical_candidates,
    generate_long_term_drift_candidates,
    generate_all_family_candidates,
    is_accessory_or_helper_joint,
    assess_multiaxial_impact,
    EventMatchResult,
    evaluate_clip_events,
)
from models import AnomalyType, AnalysisStatus, AgentSpecification, AssessmentVerdict, Severity, Finding, BodyPart
from benchmark_data import (
    BENCHMARK_MANIFEST_VERSION,
    BENCHMARK_CLIPS_HASHES,
    BENCHMARK_MANIFEST,
    get_clip_manifest,
    get_joint_intervals,
)


def test_euler_unwrapping():
    angles = [350.0, 355.0, 0.0, 5.0, 10.0]
    unwrapped = unwrap_angles(angles)
    assert len(unwrapped) == 5
    assert unwrapped[0] == 350.0
    assert unwrapped[1] == 355.0
    assert unwrapped[2] == pytest.approx(360.0)
    assert unwrapped[3] == pytest.approx(365.0)
    assert unwrapped[4] == pytest.approx(370.0)

    wrap_down = [10.0, 5.0, 0.0, 355.0, 350.0]
    unwrapped_down = unwrap_angles(wrap_down)
    assert unwrapped_down[2] == 0.0
    assert unwrapped_down[3] == pytest.approx(-5.0)
    assert unwrapped_down[4] == pytest.approx(-10.0)


def test_euler_unwrapping_smooth_transition_no_jitter():
    header = """HIERARCHY
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
Frames: 10
Frame Time: 0.033333
"""
    angles = [355.0, 357.0, 359.0, 1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0]
    rows = [f"0.0 0.0 0.0 0.0 0.0 {a:.4f}" for a in angles]
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_rotation_jitter(parsed, parsed.metadata)
        assert len(findings) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def create_synthetic_bvh(
    frame_count: int,
    frame_time: float,
    root_motion_gen,
    joint_motion_gen=None,
    has_foot: bool = True,
) -> str:
    foot_part = """    JOINT LeftFoot
    {
        OFFSET 0.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -2.0 0.0
        }
    }""" if has_foot else """    JOINT LeftProp
    {
        OFFSET 0.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -2.0 0.0
        }
    }"""

    header = f"""HIERARCHY
ROOT Hips
{{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftLeg
    {{
        OFFSET -5.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
{foot_part}
    }}
}}
MOTION
Frames: {frame_count}
Frame Time: {frame_time}
"""
    rows = []
    for t in range(frame_count):
        rx, ry, rz, r_rot_z, r_rot_x, r_rot_y = root_motion_gen(t, frame_time)
        leg_z, leg_x, leg_y = (0.0, 0.0, 0.0)
        foot_z, foot_x, foot_y = (0.0, 0.0, 0.0)
        if joint_motion_gen:
            leg_rot, foot_rot = joint_motion_gen(t, frame_time)
            leg_z, leg_x, leg_y = leg_rot
            foot_z, foot_x, foot_y = foot_rot
        rows.append(
            f"{rx:.4f} {ry:.4f} {rz:.4f} {r_rot_z:.4f} {r_rot_x:.4f} {r_rot_y:.4f} "
            f"{leg_z:.4f} {leg_x:.4f} {leg_y:.4f} "
            f"{foot_z:.4f} {foot_x:.4f} {foot_y:.4f}"
        )
    return header + "\n".join(rows) + "\n"


def test_root_discontinuity_detection():
    def motion(t, dt):
        if t == 15:
            return 100.0, 20.0, 0.0, 0.0, 0.0, 0.0
        return t * 0.1, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(30, 0.033333, motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_root_discontinuity(parsed, parsed.metadata)
        assert len(findings) > 0
        root_f = [f for f in findings if f.anomaly_type == AnomalyType.ROOT_DISCONTINUITY]
        assert len(root_f) > 0
        f = root_f[0]
        assert f.frame_start <= 16 <= f.frame_end
        assert f.affected_joint == "Hips"
        assert f.confidence >= 0.9
        assert "max_speed" in f.evidence
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_rotation_jitter_detection():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def joint_gen(t, dt):
        if 10 <= t <= 16:
            jitter = 30.0 if t % 2 == 0 else -30.0
            return (jitter, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(30, 0.033333, root_gen, joint_gen)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_rotation_jitter(parsed, parsed.metadata)
        assert len(findings) > 0
        rot_f = [f for f in findings if f.anomaly_type == AnomalyType.ROTATION_JITTER]
        assert len(rot_f) > 0
        f = rot_f[0]
        assert f.affected_joint == "LeftLeg"
        assert f.frame_start >= 10
        assert f.frame_end <= 18
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_foot_sliding_detection():
    def root_gen(t, dt):
        if 5 <= t <= 15:
            return t * 10.0, 20.0, 0.0, 0.0, 0.0, 0.0
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(25, 0.033333, root_gen)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        findings, evaluated = detect_foot_sliding(parsed, parsed.metadata, pos)
        assert evaluated is True
        assert len(findings) > 0
        assert any(f.anomaly_type == AnomalyType.PLANTED_FOOT_SLIDING for f in findings)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_uncertainty_handling_no_foot_joint():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(10, 0.033333, root_gen, has_foot=False)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        findings, evaluated = detect_foot_sliding(parsed, parsed.metadata, pos)
        assert evaluated is False
        assert len(findings) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_multi_rate_fps_invariance():
    def root_motion_func(time_sec: float):
        if 0.5 <= time_sec <= 0.6:
            return 80.0, 20.0, 0.0, 0.0, 0.0, 0.0
        return time_sec * 2.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def motion_30(t, dt):
        return root_motion_func(t * dt)

    def motion_60(t, dt):
        return root_motion_func(t * dt)

    bvh_30 = create_synthetic_bvh(60, 0.033333, motion_30)
    bvh_60 = create_synthetic_bvh(120, 0.016666, motion_60)

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f30:
        f30.write(bvh_30)
        p30 = f30.name

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f60:
        f60.write(bvh_60)
        p60 = f60.name

    try:
        parsed_30 = parse_bvh_file(p30)
        parsed_60 = parse_bvh_file(p60)

        findings_30 = detect_root_discontinuity(parsed_30, parsed_30.metadata)
        findings_60 = detect_root_discontinuity(parsed_60, parsed_60.metadata)

        assert len(findings_30) > 0
        assert len(findings_60) > 0

        t30 = (findings_30[0].time_start, findings_30[0].time_end)
        t60 = (findings_60[0].time_start, findings_60[0].time_end)

        assert abs(t30[0] - t60[0]) <= 0.05
        assert abs(t30[1] - t60[1]) <= 0.05
    finally:
        if os.path.exists(p30):
            os.remove(p30)
        if os.path.exists(p60):
            os.remove(p60)


def test_deterministic_hashes():
    def motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(10, 0.033333, motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed1 = parse_bvh_file(temp_path)
        analysis1 = analyze_bvh(parsed1, "asset-123", "2026-09-04T12:00:00Z")

        parsed2 = parse_bvh_file(temp_path)
        analysis2 = analyze_bvh(parsed2, "asset-123", "2026-09-04T12:00:00Z")

        assert analysis1.analysis_hash == analysis2.analysis_hash
        assert len(analysis1.analysis_hash) == 64

        roster1 = [AgentSpecification(agent_id="a1", role="kinematics")]
        roster2 = [AgentSpecification(agent_id="a1", role="kinematics")]
        assert compute_roster_hash(roster1) == compute_roster_hash(roster2)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_scale_invalidation_preserves_rotation_jitter_and_records_status():
    header = """HIERARCHY
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
Frames: 30
Frame Time: 0.033333
"""
    rows = []
    for t in range(30):
        rot_val = 30.0 if (10 <= t <= 16 and t % 2 == 0) else (-30.0 if (10 <= t <= 16) else 0.0)
        rows.append(f"0.0 0.0 0.0 0.0 0.0 {rot_val:.4f}")
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        assert parsed.metadata.skeleton_scale == 0.0
        analysis = analyze_bvh(parsed, "asset-zero-scale", "2026-09-04T12:00:00Z")
        assert analysis.status == AnalysisStatus.FINDINGS
        assert len(analysis.findings) > 0
        assert any(f.anomaly_type == AnomalyType.ROTATION_JITTER for f in analysis.findings)
        assert analysis.detector_status["rotation_jitter"] == "COMPLETED"
        assert analysis.detector_status["translation_jitter"] == "INCONCLUSIVE"
        assert analysis.detector_status["root_discontinuity"] == "INCONCLUSIVE"
        assert analysis.detector_status["foot_contact"] == "INCONCLUSIVE"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_coordinate_profile_non_y_up():
    header = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Spine
    {
        OFFSET 0.0 0.0 50.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 0.0 50.0
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = ["0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0" for _ in range(10)]
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        analysis = analyze_bvh(parsed, "asset-z-up", "2026-09-04T12:00:00Z")
        assert analysis.up_axis == "Z"
        assert analysis.detector_status["foot_contact"] == "INCONCLUSIVE"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_forward_kinematics_respects_custom_channel_orders():
    bvh_zxy = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Arm
    {
        OFFSET 0.0 10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT Hand
        {
            OFFSET 0.0 10.0 0.0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
                OFFSET 0.0 5.0 0.0
            }
        }
    }
}
MOTION
Frames: 1
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0   90.0 90.0 0.0   0.0 0.0 0.0
"""
    bvh_yxz = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Arm
    {
        OFFSET 0.0 10.0 0.0
        CHANNELS 3 Yrotation Xrotation Zrotation
        JOINT Hand
        {
            OFFSET 0.0 10.0 0.0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
                OFFSET 0.0 5.0 0.0
            }
        }
    }
}
MOTION
Frames: 1
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0   90.0 90.0 0.0   0.0 0.0 0.0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f1:
        f1.write(bvh_zxy)
        p1 = f1.name
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f2:
        f2.write(bvh_yxz)
        p2 = f2.name

    try:
        parsed1 = parse_bvh_file(p1)
        parsed2 = parse_bvh_file(p2)

        pos1, _ = compute_forward_kinematics(parsed1)
        pos2, _ = compute_forward_kinematics(parsed2)

        diff = any(
            abs(c1 - c2) > 1e-4
            for c1, c2 in zip(pos1["Hand"][0], pos2["Hand"][0])
        )
        assert diff
    finally:
        if os.path.exists(p1):
            os.remove(p1)
        if os.path.exists(p2):
            os.remove(p2)


def test_clean_mocap_zero_false_positives(isolated_mocap_environment):
    cmu_path = os.path.join(os.path.dirname(__file__), "fixtures", "clean_cmu_reference.bvh")
    assert os.path.exists(cmu_path)
    parsed = parse_bvh_file(cmu_path)
    analysis = analyze_bvh(parsed, "asset-clean-cmu", "2026-09-06T00:00:00Z")
    assert analysis.status == AnalysisStatus.CLEAN
    assert len(analysis.findings) == 0

    def smooth_fast_motion(t, dt):
        val = math.sin(t * 0.1) * 45.0
        return (val, 0.0, 0.0), (0.0, 0.0, 0.0)

    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(50, 0.008333, root_gen, smooth_fast_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed_fast = parse_bvh_file(temp_path)
        analysis_fast = analyze_bvh(parsed_fast, "asset-clean-fast", "2026-09-06T00:00:00Z")
        assert analysis_fast.status == AnalysisStatus.CLEAN
        assert len(analysis_fast.findings) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_all_seven_domains_in_detector_status():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(15, 0.033333, root_gen)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        analysis = analyze_bvh(parsed, "asset-7-domains", "2026-09-08T12:00:00Z")
        expected_domains = [
            "file_syntax",
            "sensor_tracking",
            "representation_singularities",
            "biomechanical_rom",
            "environmental_contact",
            "volumetric_collision",
            "physical_dynamics",
        ]
        for domain in expected_domains:
            assert domain in analysis.detector_status
            assert analysis.detector_status[domain] == "COMPLETED"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_sensor_tracking_flatline_detection():
    def root_motion(t, dt):
        return t * 1.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def frozen_leg_motion(t, dt):
        if 8 <= t <= 16:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (float(t), 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion, frozen_leg_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        findings = detect_sensor_tracking_artifacts(parsed, parsed.metadata, pos)
        flat_findings = [f for f in findings if f.anomaly_type == AnomalyType.OPTICAL_OCCLUSION_FLATLINE]
        assert len(flat_findings) > 0
        f = flat_findings[0]
        assert f.affected_joint in ("LeftLeg", "LeftFoot")
        assert f.confidence >= 0.90
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_sensor_tracking_marker_swap_detection():
    header = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftFoot
    {
        OFFSET -10.0 -20.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -2.0 0.0
        }
    }
    JOINT RightFoot
    {
        OFFSET 10.0 -20.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -2.0 0.0
        }
    }
}
MOTION
Frames: 20
Frame Time: 0.033333
"""
    rows = []
    for t in range(20):
        rows.append("0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0")
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        for t in range(8, 12):
            tmp = pos["LeftFoot"][t]
            pos["LeftFoot"][t] = pos["RightFoot"][t]
            pos["RightFoot"][t] = tmp

        findings = detect_sensor_tracking_artifacts(parsed, parsed.metadata, pos)
        swap_findings = [f for f in findings if f.anomaly_type == AnomalyType.OPTICAL_MARKER_SWAP]
        assert len(swap_findings) > 0
        assert swap_findings[0].affected_joint == "LeftFoot"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_representation_singularities_euler_gimbal_lock_flip():
    header = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Arm
    {
        OFFSET 0.0 10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 5.0 0.0
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = []
    for t in range(10):
        if t < 5:
            arm_z, arm_x, arm_y = 0.0, 88.0, 0.0
        else:
            arm_z, arm_x, arm_y = 180.0, 88.0, 180.0
        rows.append(f"0.0 20.0 0.0 0.0 0.0 0.0 {arm_z:.4f} {arm_x:.4f} {arm_y:.4f}")
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_representation_singularities(parsed, parsed.metadata)
        gimbal_f = [f for f in findings if f.anomaly_type == AnomalyType.EULER_GIMBAL_LOCK_FLIP]
        assert len(gimbal_f) > 0
        assert gimbal_f[0].affected_joint == "Arm"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_biomechanical_rom_hyperextension():
    header = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftKnee
    {
        OFFSET 0.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -10.0 0.0
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = []
    for t in range(10):
        knee_x = -25.0 if 3 <= t <= 7 else 10.0
        rows.append(f"0.0 20.0 0.0 0.0 0.0 0.0 0.0 {knee_x:.4f} 0.0")
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        findings = detect_biomechanical_violations(parsed, parsed.metadata, pos)
        rom_f = [f for f in findings if f.anomaly_type == AnomalyType.ROM_HYPEREXTENSION]
        assert len(rom_f) > 0
        assert rom_f[0].affected_joint == "LeftKnee"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_biomechanical_bone_length_violation():
    header = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Shin
    {
        OFFSET 0.0 -20.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -5.0 0.0
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = [f"0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0" for _ in range(10)]
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        for t in range(3, 7):
            pos["Shin"][t] = [0.0, 30.0, 0.0]

        findings = detect_biomechanical_violations(parsed, parsed.metadata, pos)
        bone_f = [f for f in findings if f.anomaly_type == AnomalyType.BONE_LENGTH_VIOLATION]
        assert len(bone_f) > 0
        assert bone_f[0].affected_joint == "Shin"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_environmental_contact_ground_penetration_and_hover():
    header = """HIERARCHY
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
            OFFSET 0.0 -2.0 0.0
        }
    }
}
MOTION
Frames: 40
Frame Time: 0.033333
"""
    rows_pen = []
    for t in range(40):
        root_y = 4.0 if (12 <= t <= 18) else 10.0
        rows_pen.append(f"0.0 {root_y:.4f} 0.0 0.0 0.0 0.0 0.0 0.0 0.0")
    bvh_pen = header + "\n".join(rows_pen) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_pen)
        p_pen = f.name

    rows_hov = []
    for t in range(40):
        root_y = 10.0 if t < 10 else 50.0
        rows_hov.append(f"0.0 {root_y:.4f} 0.0 0.0 0.0 0.0 0.0 0.0 0.0")
    bvh_hov = header + "\n".join(rows_hov) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_hov)
        p_hov = f.name

    try:
        parsed_pen = parse_bvh_file(p_pen)
        pos_pen, _ = compute_forward_kinematics(parsed_pen)
        findings_pen, _ = detect_contact_and_ground(parsed_pen, parsed_pen.metadata, pos_pen)
        pen_f = [f for f in findings_pen if f.anomaly_type == AnomalyType.GROUND_PENETRATION]
        assert len(pen_f) > 0
        assert pen_f[0].affected_joint == "LeftFoot"

        parsed_hov = parse_bvh_file(p_hov)
        pos_hov, _ = compute_forward_kinematics(parsed_hov)
        findings_hov, _ = detect_contact_and_ground(parsed_hov, parsed_hov.metadata, pos_hov)
        hov_f = [f for f in findings_hov if f.anomaly_type == AnomalyType.GROUND_HOVERING]
        assert len(hov_f) > 0
    finally:
        if os.path.exists(p_pen):
            os.remove(p_pen)
        if os.path.exists(p_hov):
            os.remove(p_hov)


def test_volumetric_self_collision_detection():
    header = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftUpLeg
    {
        OFFSET -5.0 -5.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT LeftLeg
        {
            OFFSET 0.0 -10.0 0.0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
                OFFSET 0.0 -5.0 0.0
            }
        }
    }
    JOINT RightUpLeg
    {
        OFFSET 5.0 -5.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT RightLeg
        {
            OFFSET 0.0 -10.0 0.0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
                OFFSET 0.0 -5.0 0.0
            }
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = ["0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0   0.0 0.0 0.0   0.0 0.0 0.0   0.0 0.0 0.0" for _ in range(10)]
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        for t in range(3, 7):
            pos["LeftUpLeg"][t] = [-1.0, 15.0, 0.0]
            pos["LeftLeg"][t] = [1.0, 5.0, 0.0]
            pos["RightUpLeg"][t] = [1.0, 15.0, 0.0]
            pos["RightLeg"][t] = [-1.0, 5.0, 0.0]

        findings = detect_volumetric_self_collisions(parsed, parsed.metadata, pos)
        coll_f = [f for f in findings if f.anomaly_type == AnomalyType.LIMB_SELF_COLLISION]
        assert len(coll_f) > 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_physical_dynamics_violations():
    header = """HIERARCHY
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
            OFFSET 0.0 -2.0 0.0
        }
    }
}
MOTION
Frames: 30
Frame Time: 0.033333
"""
    rows = []
    for t in range(30):
        y_val = 50.0 + (t * t * 1.5)
        rows.append(f"0.0 {y_val:.4f} 0.0 0.0 0.0 0.0 0.0 0.0 0.0")
    bvh_text = header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        findings = detect_physical_dynamics(parsed, parsed.metadata, pos)
        grav_f = [f for f in findings if f.anomaly_type == AnomalyType.BALLISTIC_GRAVITY_VIOLATION]
        assert len(grav_f) > 0
        assert grav_f[0].affected_joint == "Hips"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.fixture
def isolated_mocap_environment():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    uploads_path = os.path.join(backend_dir, "uploads")
    backup_path = os.path.join(backend_dir, "uploads_isolated_hidden")
    was_renamed = False
    if os.path.exists(uploads_path):
        os.rename(uploads_path, backup_path)
        was_renamed = True
    try:
        assert not os.path.exists(uploads_path)
        yield uploads_path
    finally:
        if was_renamed and os.path.exists(backup_path):
            if os.path.exists(uploads_path):
                shutil.rmtree(uploads_path)
            os.rename(backup_path, uploads_path)


@pytest.fixture
def right_arm_pop_fixture():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    clip_path = os.path.join(fixtures_dir, "02_StepFwd_RightArmSolvePop.bvh")
    expected_hash = "5a4a483b6c39ad4202b28996af019368927f9dc17a5487e63bbd6c4d504c4e16"
    assert os.path.isfile(clip_path)
    with open(clip_path, "rb") as f:
        computed = hashlib.sha256(f.read()).hexdigest()
    assert computed == expected_hash
    assert len(computed) == 64
    return clip_path


def test_isolated_test_runner_environment(isolated_mocap_environment):
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    uploads_path = os.path.join(backend_dir, "uploads")
    assert not os.path.exists(uploads_path)


def test_benchmark_fixtures_integrity():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    assert os.path.isdir(fixtures_dir)
    for fname, expected_hash in BENCHMARK_CLIPS_HASHES.items():
        fpath = os.path.join(fixtures_dir, fname)
        assert os.path.isfile(fpath), f"Missing fixture: {fname}"
        with open(fpath, "rb") as f:
            computed_hash = hashlib.sha256(f.read()).hexdigest()
        assert computed_hash == expected_hash, f"SHA-256 mismatch for {fname}"
        assert len(computed_hash) == 64


def test_benchmark_manifest_intervals():
    assert BENCHMARK_MANIFEST_VERSION == "1.0.0"
    pop_manifest = get_clip_manifest("02_StepFwd_RightArmSolvePop.bvh")
    assert pop_manifest["originating_joints"] == ["RightArm"]
    assert "RightForeArm" in pop_manifest["descendant_joints"]
    assert "RightHand" in pop_manifest["descendant_joints"]
    intervals = get_joint_intervals("02_StepFwd_RightArmSolvePop.bvh", "RightArm")
    assert len(intervals["confirmed_defective"]) == 1
    assert intervals["confirmed_defective"][0]["frames_0_based"] == [79, 84]
    assert intervals["confirmed_defective"][0]["frames_1_based"] == [80, 85]
    assert intervals["confirmed_defective"][0]["role"] == "originating"
    assert len(intervals["confirmed_acceptable"]) > 0
    assert len(intervals["transition_uncertain"]) > 0


def test_right_arm_solve_pop_detector_miss(right_arm_pop_fixture, isolated_mocap_environment):
    parsed = parse_bvh_file(right_arm_pop_fixture)
    analysis = analyze_bvh(parsed, "asset-02-right-arm-pop", "2026-09-09T00:00:00Z")
    detected_arm_defects = [
        f for f in analysis.findings
        if f.affected_joint == "RightArm" and (f.frame_start <= 84 and f.frame_end >= 79)
    ]
    assert len(detected_arm_defects) > 0
    pop = detected_arm_defects[0]
    assert pop.affected_joint == "RightArm"
    assert pop.frame_start <= 84 and pop.frame_end >= 79
    assert pop.verdict in (AssessmentVerdict.LIKELY_VISIBLE_DEFECT, AssessmentVerdict.REVIEW)
    assert pop.evidence["originating_joint"] == "RightArm"
    assert pop.evidence["max_descendant_displacement"] > 0.0


def test_detect_motion_pops_single_frame_spike():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def spike_motion(t, dt):
        if t == 15:
            return (45.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(30, 0.033333, root_gen, spike_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_motion_pops(parsed, parsed.metadata)
        assert len(findings) > 0
        leg_spikes = [f for f in findings if f.affected_joint == "LeftLeg"]
        assert len(leg_spikes) > 0
        spike = leg_spikes[0]
        assert spike.frame_start <= 15 <= spike.frame_end
        assert spike.verdict in (AssessmentVerdict.LIKELY_VISIBLE_DEFECT, AssessmentVerdict.REVIEW)
        assert spike.evidence["measured_value"] >= 15.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_detect_motion_pops_multi_frame_burst():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def burst_motion(t, dt):
        if 12 <= t <= 16:
            val = 35.0 if t % 2 == 0 else -25.0
            return (val, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(35, 0.033333, root_gen, burst_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_motion_pops(parsed, parsed.metadata)
        assert len(findings) > 0
        burst_f = [f for f in findings if f.affected_joint == "LeftLeg"]
        assert len(burst_f) > 0
        f = burst_f[0]
        assert f.frame_start <= 14 <= f.frame_end
        assert f.evidence["pop_type"] == "multi_frame_burst"
        assert f.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT
        assert f.evidence["max_descendant_displacement"] > 0.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_detect_motion_pops_persistent_step():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def step_motion(t, dt):
        if t >= 15:
            return (30.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(35, 0.033333, root_gen, step_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_motion_pops(parsed, parsed.metadata)
        assert len(findings) > 0
        step_f = [f for f in findings if f.affected_joint == "LeftLeg"]
        assert len(step_f) > 0
        f = step_f[0]
        assert f.frame_start <= 16 and f.frame_end >= 14
        assert f.evidence["pop_type"] == "persistent_trajectory_step"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_detect_motion_pops_boundary_one_sided_context():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def boundary_motion(t, dt):
        if t <= 1:
            return (40.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(20, 0.033333, root_gen, boundary_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        all_findings = detect_motion_pops(parsed, parsed.metadata, include_all_verdicts=True)
        boundary_f = [f for f in all_findings if f.evidence.get("pop_type") == "boundary_event"]
        assert len(boundary_f) > 0
        assert boundary_f[0].verdict == AssessmentVerdict.INCONCLUSIVE
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_detect_motion_pops_multi_window_and_unstable_anchors():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def chaotic_motion(t, dt):
        if 18 <= t <= 22:
            return (50.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        jitter = 20.0 if t % 2 == 0 else -20.0
        return (jitter, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(40, 0.033333, root_gen, chaotic_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_motion_pops(parsed, parsed.metadata, include_all_verdicts=True)
        assert len(findings) > 0
        for f in findings:
            assert "evaluated_windows_sec" in f.evidence
            assert f.evidence["evaluated_windows_sec"] == [0.05, 0.10, 0.25]
            if f.evidence.get("anchor_unstable") is True:
                assert "uncertainty" in f.evidence
                assert f.evidence["uncertainty"] > 0.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_early_rule_based_impact_assessment_verdicts():
    v1, s1, c1 = assess_motion_pop_candidate(
        peak_departure=30.0,
        descendant_displacement=15.0,
        has_descendants=True,
        anchor_unstable=False,
        context_insufficient=False,
        scale=170.0,
        is_boundary=False,
    )
    assert v1 == AssessmentVerdict.LIKELY_VISIBLE_DEFECT
    assert s1 == Severity.CRITICAL
    assert c1 >= 0.90

    v2, s2, c2 = assess_motion_pop_candidate(
        peak_departure=11.0,
        descendant_displacement=1.2,
        has_descendants=True,
        anchor_unstable=False,
        context_insufficient=False,
        scale=170.0,
        is_boundary=False,
    )
    assert v2 == AssessmentVerdict.REVIEW
    assert s2 == Severity.MEDIUM

    v3, s3, c3 = assess_motion_pop_candidate(
        peak_departure=4.0,
        descendant_displacement=0.3,
        has_descendants=True,
        anchor_unstable=False,
        context_insufficient=False,
        scale=170.0,
        is_boundary=False,
    )
    assert v3 == AssessmentVerdict.NUMERICAL_ONLY
    assert s3 == Severity.LOW

    v4, s4, c4 = assess_motion_pop_candidate(
        peak_departure=25.0,
        descendant_displacement=10.0,
        has_descendants=True,
        anchor_unstable=True,
        context_insufficient=True,
        scale=170.0,
        is_boundary=True,
    )
    assert v4 == AssessmentVerdict.INCONCLUSIVE


def test_analysis_hash_recomputation_after_assessment():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(20, 0.033333, root_gen)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        analysis = analyze_bvh(parsed, "asset-hash-check", "2026-09-09T12:00:00Z")
        expected_hash = compute_analysis_hash(
            parsed.raw_content_hash,
            parsed.metadata.skeleton_signature,
            parsed.metadata.parser_version,
            DETECTOR_VERSION,
            analysis.findings,
        )
        assert analysis.analysis_hash == expected_hash
        assert len(analysis.analysis_hash) == 64
        assert "motion_pops" in analysis.detector_status
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_pops_jumps_positive():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def pop_leg_motion(t, dt):
        if t == 15:
            return (45.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(30, 0.033333, root_motion, pop_leg_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_pop_jump_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        leg_cands = [c for c in candidates if c.joint == "LeftLeg"]
        assert len(leg_cands) > 0
        cand = leg_cands[0]
        assert cand.family == "pops_jumps"
        assert cand.has_context is True
        assert cand.verdict in (AssessmentVerdict.LIKELY_VISIBLE_DEFECT, AssessmentVerdict.REVIEW)
        assert cand.peak_frame == 15
        finding = cand.to_finding(parsed.metadata.frame_time)
        assert finding.affected_joint == "LeftLeg"
        assert finding.frame_start <= 15 <= finding.frame_end
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_pops_jumps_difficult_acceptable():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def smooth_leg_motion(t, dt):
        val = math.sin(t * 0.1) * 30.0
        return (val, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(35, 0.033333, root_motion, smooth_leg_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_pop_jump_candidates(parsed, parsed.metadata)
        visible_defects = [c for c in candidates if c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_defects) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_pops_jumps_missing_context():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(4, 0.033333, root_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_pop_jump_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        inconclusive = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(inconclusive) > 0
        assert inconclusive[0].missing_context_reason == "insufficient_frames"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_repeated_jitter_positive():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def jitter_leg_motion(t, dt):
        if 8 <= t <= 18:
            val = 35.0 if t % 2 == 0 else -35.0
            return (val, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(30, 0.033333, root_motion, jitter_leg_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_repeated_jitter_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        jitter_cands = [c for c in candidates if c.joint == "LeftLeg" and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(jitter_cands) > 0
        cand = jitter_cands[0]
        assert cand.family == "repeated_jitter"
        assert cand.evidence["sustained_oscillation"] is True
        assert cand.evidence["significant_displacement"] is True
        assert cand.evidence["sign_alternation_ratio"] >= 0.38
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_repeated_jitter_difficult_acceptable():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def rapid_athletic_turn(t, dt):
        angles = [0.0, 2.0, 6.0, 15.0, 35.0, 60.0, 80.0, 90.0, 92.0, 93.0]
        val = angles[t] if t < len(angles) else 93.0
        return (val, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion, rapid_athletic_turn)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_repeated_jitter_candidates(parsed, parsed.metadata)
        visible_defects = [c for c in candidates if c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_defects) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_repeated_jitter_missing_context():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(4, 0.033333, root_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_repeated_jitter_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        inconclusive = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(inconclusive) > 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_freezes_positive():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def freezing_leg_motion(t, dt):
        if 8 <= t <= 15:
            return (40.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (float(t) * 5.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(28, 0.033333, root_motion, freezing_leg_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_freeze_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        leg_freezes = [c for c in candidates if c.joint in ("LeftLeg", "LeftFoot") and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(leg_freezes) > 0
        cand = leg_freezes[0]
        assert cand.family == "freezes"
        assert cand.anomaly_type == AnomalyType.OPTICAL_OCCLUSION_FLATLINE
        assert cand.evidence["active_pre_motion"] is True
        assert cand.evidence["continuation_mismatch"] is True
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_freezes_difficult_acceptable():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def intentional_smooth_hold(t, dt):
        smooth_curve = [
            12.0, 8.0, 4.0, 1.0, 0.2,
            0.0, 0.0, 0.0, 0.0, 0.0,
            0.2, 1.0, 4.0, 8.0, 12.0,
        ]
        val = smooth_curve[t] if t < len(smooth_curve) else 12.0
        return (val, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion, intentional_smooth_hold)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_freeze_candidates(parsed, parsed.metadata)
        visible_freezes = [c for c in candidates if c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_freezes) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_freezes_missing_context():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def flat_from_start(t, dt):
        if t <= 10:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (float(t - 10) * 3.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion, flat_from_start)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_freeze_candidates(parsed, parsed.metadata)
        inconclusive = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(inconclusive) > 0
        assert inconclusive[0].missing_context_reason == "boundary_context_missing_for_freeze"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_foot_sliding_positive():
    def sliding_root(t, dt):
        return float(t) * 2.5, 22.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(25, 0.033333, sliding_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_foot_sliding_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        slide_cands = [c for c in candidates if c.anomaly_type == AnomalyType.PLANTED_FOOT_SLIDING and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(slide_cands) > 0
        cand = slide_cands[0]
        assert cand.family == "foot_sliding"
        assert cand.joint == "LeftFoot"
        assert cand.physical_displacement > 0.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_foot_sliding_difficult_acceptable():
    def stationary_planted_root(t, dt):
        return 0.0, 22.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(25, 0.033333, stationary_planted_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_foot_sliding_candidates(parsed, parsed.metadata)
        visible_slides = [c for c in candidates if c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_slides) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_foot_sliding_missing_context():
    def root_gen(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(20, 0.033333, root_gen, has_foot=False)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_foot_sliding_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        inconclusive = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(inconclusive) > 0
        assert inconclusive[0].missing_context_reason == "missing_foot_joints"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_ground_contact_positive():
    def sinking_root(t, dt):
        y = 12.0 if 10 <= t <= 16 else 22.0
        return 0.0, y, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(25, 0.033333, sinking_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_ground_contact_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        pen_cands = [c for c in candidates if c.anomaly_type == AnomalyType.GROUND_PENETRATION and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(pen_cands) > 0
        cand = pen_cands[0]
        assert cand.family == "ground_contact"
        assert cand.joint == "LeftFoot"
        assert cand.physical_displacement > 0.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_ground_contact_difficult_acceptable():
    def ballistic_jump_root(t, dt):
        if 5 <= t <= 20:
            jump_h = 22.0 + math.sin((t - 5) / 15.0 * math.pi) * 20.0
            return 0.0, jump_h, 0.0, 0.0, 0.0, 0.0
        return 0.0, 22.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(26, 0.033333, ballistic_jump_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_ground_contact_candidates(parsed, parsed.metadata)
        visible_hover = [c for c in candidates if c.anomaly_type == AnomalyType.GROUND_HOVERING and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_hover) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_ground_contact_missing_context():
    def ungrounded_float_root(t, dt):
        return 0.0, 60.0 + math.sin(t * 0.2) * 15.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(25, 0.033333, ungrounded_float_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_ground_contact_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        ungrounded = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(ungrounded) > 0
        assert ungrounded[0].missing_context_reason == "ungrounded_scene"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_biomechanical_positive():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def hyperextended_leg(t, dt):
        if 8 <= t <= 14:
            return (-35.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (10.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion, hyperextended_leg)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_biomechanical_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        rom_cands = [c for c in candidates if c.anomaly_type == AnomalyType.ROM_HYPEREXTENSION and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(rom_cands) > 0
        cand = rom_cands[0]
        assert cand.family == "biomechanical"
        assert cand.joint == "LeftLeg"
        assert cand.metric_value <= -30.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_biomechanical_difficult_acceptable():
    def root_motion(t, dt):
        return 0.0, 20.0, 0.0, 0.0, 0.0, 0.0

    def deep_squat_leg(t, dt):
        return (138.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion, deep_squat_leg)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_biomechanical_candidates(parsed, parsed.metadata)
        visible_rom = [c for c in candidates if c.joint == "LeftLeg" and c.anomaly_type == AnomalyType.ROM_HYPEREXTENSION and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_rom) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_biomechanical_missing_context():
    bvh_text = """HIERARCHY
ROOT BaseObject
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT SubNode
    {
        OFFSET 0.0 10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 2.0 0.0
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 20.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_biomechanical_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        inconclusive = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(inconclusive) > 0
        assert inconclusive[0].missing_context_reason == "missing_biomechanical_joints"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_long_term_drift_positive():
    def drifting_yaw_root(t, dt):
        yaw = float(t) * 1.0
        return 0.0, 22.0, 0.0, 0.0, 0.0, yaw

    bvh_text = create_synthetic_bvh(30, 0.033333, drifting_yaw_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_long_term_drift_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        drift_cands = [c for c in candidates if c.anomaly_type == AnomalyType.LONG_TERM_DRIFT and c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(drift_cands) > 0
        cand = drift_cands[0]
        assert cand.family == "long_term_drift"
        assert cand.joint == "Hips"
        assert cand.metric_value >= 10.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_long_term_drift_difficult_acceptable():
    def clean_stationary_root(t, dt):
        return 0.0, 22.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(30, 0.033333, clean_stationary_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_long_term_drift_candidates(parsed, parsed.metadata)
        visible_drift = [c for c in candidates if c.verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT]
        assert len(visible_drift) == 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_candidate_long_term_drift_missing_context():
    def short_root(t, dt):
        return 0.0, 22.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(6, 0.033333, short_root)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        candidates = generate_long_term_drift_candidates(parsed, parsed.metadata)
        assert len(candidates) > 0
        inconclusive = [c for c in candidates if c.verdict == AssessmentVerdict.INCONCLUSIVE and not c.has_context]
        assert len(inconclusive) > 0
        assert inconclusive[0].missing_context_reason == "insufficient_duration_for_drift"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_generate_all_family_candidates_dispatcher():
    def root_motion(t, dt):
        return 0.0, 22.0, 0.0, 0.0, 0.0, 0.0

    bvh_text = create_synthetic_bvh(25, 0.033333, root_motion)
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        all_cands = generate_all_family_candidates(parsed, parsed.metadata)
        expected_families = [
            "pops_jumps",
            "repeated_jitter",
            "freezes",
            "foot_sliding",
            "ground_contact",
            "biomechanical",
            "long_term_drift",
        ]
        for fam in expected_families:
            assert fam in all_cands
            assert isinstance(all_cands[fam], list)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_multiaxial_impact_assessment_all_axes():
    v1, s1, c1, d1 = assess_multiaxial_impact(
        family="pops_jumps",
        joint_name="RightArm",
        measured_metric=50.0,
        threshold=20.0,
        physical_disp=15.0,
        frame_span=2,
        dt=0.016667,
        skeleton_scale=100.0,
        has_context=True,
    )
    assert v1 == AssessmentVerdict.LIKELY_VISIBLE_DEFECT
    assert s1 in (Severity.HIGH, Severity.CRITICAL)
    assert c1 >= 0.85
    assert d1["numerical_abnormality"]["ratio"] == 2.5
    assert d1["duration"]["category"] == "transient"
    assert d1["contextual_reliability"]["has_context"] is True

    v2, s2, c2, d2 = assess_multiaxial_impact(
        family="sensor_tracking",
        joint_name="LeftHand_helper",
        measured_metric=10.0,
        threshold=5.0,
        physical_disp=0.2,
        frame_span=5,
        dt=0.016667,
        skeleton_scale=100.0,
        has_context=True,
    )
    assert v2 == AssessmentVerdict.NUMERICAL_ONLY
    assert s2 == Severity.LOW
    assert d2["contextual_reliability"]["is_helper_joint"] is True
    assert d2["duration"]["category"] == "sustained"

    v3, s3, c3, d3 = assess_multiaxial_impact(
        family="foot_sliding",
        joint_name="RightFoot",
        measured_metric=25.0,
        threshold=20.0,
        physical_disp=1.2,
        frame_span=1,
        dt=0.016667,
        skeleton_scale=100.0,
        has_context=True,
        is_ground_supported=True,
    )
    assert v3 == AssessmentVerdict.REVIEW
    assert s3 == Severity.MEDIUM
    assert d3["duration"]["category"] == "single_frame"
    assert d3["contextual_reliability"]["is_ground_supported"] is True

    v4, s4, c4, d4 = assess_multiaxial_impact(
        family="biomechanical",
        joint_name="Spine",
        measured_metric=100.0,
        threshold=10.0,
        physical_disp=50.0,
        frame_span=3,
        dt=0.016667,
        skeleton_scale=0.0,
        has_context=False,
    )
    assert v4 == AssessmentVerdict.INCONCLUSIVE
    assert d4["contextual_reliability"]["has_context"] is False


def test_is_accessory_or_helper_joint():
    helper_joint_names = [
        "LeftHand_helper",
        "RightElbow_helper",
        "C_Left1LegTasselJoint0",
        "C_CenterLragJoint2",
        "RD_Left1SwordJoint0",
        "EXT_CollarRight1",
        "Tongue4",
        "Jaw",
        "MouthRiggingOffset",
        "LeftInHandPinky",
        "RightFingerBase",
    ]
    for name in helper_joint_names:
        assert is_accessory_or_helper_joint(name) is True

    primary_joint_names = [
        "Hips",
        "LeftArm",
        "RightArm",
        "LeftForeArm",
        "RightForeArm",
        "LeftHand",
        "RightHand",
        "LeftUpLeg",
        "RightUpLeg",
        "LeftLeg",
        "RightLeg",
        "LeftFoot",
        "RightFoot",
        "Head",
        "Spine",
    ]
    for name in primary_joint_names:
        assert is_accessory_or_helper_joint(name) is False


def test_reclassify_imperceptible_sensor_noise():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    clip5_path = os.path.join(fixtures_dir, "05_StartWalk_FullBodyFrameDropout.bvh")
    parsed = parse_bvh_file(clip5_path)

    analysis_primary = analyze_bvh(parsed, "clip5_primary", "2026-09-09T00:00:00Z", include_all_verdicts=False)
    analysis_all = analyze_bvh(parsed, "clip5_all", "2026-09-09T00:00:00Z", include_all_verdicts=True)

    assert len(analysis_primary.findings) < len(analysis_all.findings)
    assert len(analysis_primary.findings) < 50
    assert len(analysis_all.findings) > 150

    primary_verdicts = {f.verdict for f in analysis_primary.findings}
    assert AssessmentVerdict.NUMERICAL_ONLY not in primary_verdicts

    all_verdicts = {f.verdict for f in analysis_all.findings}
    assert AssessmentVerdict.NUMERICAL_ONLY in all_verdicts

    hips_discontinuity = [
        f for f in analysis_primary.findings
        if f.affected_joint == "Hips" and f.anomaly_type == AnomalyType.ROOT_DISCONTINUITY
    ]
    assert len(hips_discontinuity) > 0
    assert hips_discontinuity[0].verdict == AssessmentVerdict.LIKELY_VISIBLE_DEFECT


def test_strict_1to1_event_matching_logic():
    manifest = {
        "confirmed_defective": [
            {
                "joint": "Hips",
                "role": "originating",
                "frames_0_based": [10, 15],
                "peak_frame": 12,
                "anomaly_type": "ROOT_DISCONTINUITY",
            }
        ],
        "confirmed_acceptable": {
            "Hips": [[0, 5], [20, 30]],
            "LeftFoot": [[0, 30]],
        },
        "transition_uncertain": {
            "Hips": [[6, 9], [16, 19]],
        },
        "originating_joints": ["Hips"],
    }
    dt = 0.016667

    f_matched = Finding(
        finding_id="f_valid",
        affected_joint="Hips",
        affected_body_part=BodyPart.PELVIS,
        frame_start=11,
        frame_end=15,
        time_start=0.18,
        time_end=0.25,
        anomaly_type=AnomalyType.ROOT_DISCONTINUITY,
        severity=Severity.HIGH,
        confidence=0.95,
        evidence={},
        detector_version=DETECTOR_VERSION,
        explanation="",
        verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
        peak_frame=13,
    )
    f_duplicate = Finding(
        finding_id="f_dup",
        affected_joint="Hips",
        affected_body_part=BodyPart.PELVIS,
        frame_start=12,
        frame_end=14,
        time_start=0.20,
        time_end=0.23,
        anomaly_type=AnomalyType.TRANSLATION_JITTER,
        severity=Severity.MEDIUM,
        confidence=0.80,
        evidence={},
        detector_version=DETECTOR_VERSION,
        explanation="",
        verdict=AssessmentVerdict.REVIEW,
        peak_frame=13,
    )
    f_unmatched_joint = Finding(
        finding_id="f_wrong_joint",
        affected_joint="LeftFoot",
        affected_body_part=BodyPart.FOOT,
        frame_start=22,
        frame_end=26,
        time_start=0.36,
        time_end=0.43,
        anomaly_type=AnomalyType.PLANTED_FOOT_SLIDING,
        severity=Severity.HIGH,
        confidence=0.90,
        evidence={},
        detector_version=DETECTOR_VERSION,
        explanation="",
        verdict=AssessmentVerdict.LIKELY_VISIBLE_DEFECT,
        peak_frame=24,
    )

    findings = [f_matched, f_duplicate, f_unmatched_joint]
    res = evaluate_clip_events("synthetic_test", findings, manifest, dt)

    assert res.total_gt_events == 1
    assert res.matched_gt_events == 1
    assert res.confirmed_recall == 1.0
    assert res.review_inclusive_recall == 1.0
    assert res.defective_frame_coverage > 0.8
    assert res.duplicate_penalties == 1
    assert len(res.duplicate_detections) == 1
    assert res.duplicate_detections[0]["detection_id"] == "f_dup"
    assert len(res.unmatched_detections) == 1
    assert res.unmatched_detections[0]["detection_id"] == "f_wrong_joint"
    assert res.excess_good_frames_flagged == 5


def test_held_out_evaluation_root_yaw_drift():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    clip_name = "03_StanceTurnaround_RootYawDrift.bvh"
    clip_path = os.path.join(fixtures_dir, clip_name)
    manifest = get_clip_manifest(clip_name)
    parsed = parse_bvh_file(clip_path)

    analysis = analyze_bvh(parsed, "heldout_clip03", "2026-09-09T00:00:00Z")
    res = evaluate_clip_events(clip_name, analysis.findings, manifest, parsed.metadata.frame_time)

    assert res.clip_name == clip_name
    assert res.total_gt_events == 1
    assert res.matched_gt_events == 1
    assert res.confirmed_recall == 1.0
    assert res.review_inclusive_recall == 1.0
    assert res.defective_frame_coverage == 1.0
    assert res.excess_width_penalties == 0
    assert len(res.matched_pairs) == 1

    matched = res.matched_pairs[0]
    assert matched["joint"] == "Hips"
    assert matched["gt_interval"] == [2, 8]
    assert matched["iou"] >= 0.40
    assert matched["peak_distance"] <= 3


def test_held_out_evaluation_full_body_frame_dropout():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    clip_name = "05_StartWalk_FullBodyFrameDropout.bvh"
    clip_path = os.path.join(fixtures_dir, clip_name)
    manifest = get_clip_manifest(clip_name)
    parsed = parse_bvh_file(clip_path)

    analysis = analyze_bvh(parsed, "heldout_clip05", "2026-09-09T00:00:00Z")
    res = evaluate_clip_events(clip_name, analysis.findings, manifest, parsed.metadata.frame_time)

    assert res.clip_name == clip_name
    assert res.total_gt_events == 1
    assert res.matched_gt_events == 1
    assert res.confirmed_recall == 1.0
    assert res.review_inclusive_recall == 1.0
    assert res.defective_frame_coverage == 1.0
    assert res.excess_good_frames_flagged == 0
    assert res.excess_width_penalties == 0
    assert len(res.matched_pairs) == 1

    matched = res.matched_pairs[0]
    assert matched["joint"] == "Hips"
    assert matched["gt_interval"] == [47, 47]
    assert matched["iou"] >= 0.40
    assert matched["peak_distance"] <= 3
    assert len(analysis.findings) < 50


def test_frozen_benchmark_all_clips_evaluation():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    clip_order = [
        "01_WalkFwd_Loop_RightContactDropout.bvh",
        "02_StepFwd_RightArmSolvePop.bvh",
        "03_StanceTurnaround_RootYawDrift.bvh",
        "04_StepBwd_RootPositionSpike.bvh",
        "05_StartWalk_FullBodyFrameDropout.bvh",
        "clean_cmu_reference.bvh",
    ]
    evaluation_reports: Dict[str, EventMatchResult] = {}

    for name in clip_order:
        fpath = os.path.join(fixtures_dir, name)
        manifest = get_clip_manifest(name)
        parsed = parse_bvh_file(fpath)
        analysis = analyze_bvh(parsed, name, "2026-09-09T00:00:00Z")
        res = evaluate_clip_events(name, analysis.findings, manifest, parsed.metadata.frame_time)
        evaluation_reports[name] = res

    clean_res = evaluation_reports["clean_cmu_reference.bvh"]
    assert clean_res.matched_gt_events == 0
    assert clean_res.excess_good_frames_flagged == 0
    assert clean_res.duplicate_penalties == 0
    assert clean_res.joint_attribution_accuracy == 1.0

    c01_res = evaluation_reports["01_WalkFwd_Loop_RightContactDropout.bvh"]
    assert c01_res.confirmed_recall == 1.0
    assert c01_res.defective_frame_coverage == 1.0

    c02_res = evaluation_reports["02_StepFwd_RightArmSolvePop.bvh"]
    assert c02_res.defective_frame_coverage == 1.0
    assert any(p["joint"] == "RightArm" for p in c02_res.matched_pairs)

    c03_res = evaluation_reports["03_StanceTurnaround_RootYawDrift.bvh"]
    assert c03_res.confirmed_recall == 1.0
    assert c03_res.defective_frame_coverage == 1.0
    assert any(p["joint"] == "Hips" for p in c03_res.matched_pairs)

    c04_res = evaluation_reports["04_StepBwd_RootPositionSpike.bvh"]
    assert c04_res.confirmed_recall == 1.0
    assert c04_res.defective_frame_coverage == 1.0
    assert any(p["joint"] == "Hips" for p in c04_res.matched_pairs)

    c05_res = evaluation_reports["05_StartWalk_FullBodyFrameDropout.bvh"]
    assert c05_res.confirmed_recall == 1.0
    assert c05_res.defective_frame_coverage == 1.0
    assert c05_res.excess_good_frames_flagged == 0
    assert any(p["joint"] == "Hips" for p in c05_res.matched_pairs)







import os
import math
import tempfile
import pytest

from bvh_parser import parse_bvh_file, compute_rest_pose_kinematics
from detector import (
    SharedMotionRepresentation,
    build_shared_motion_representation,
    compute_forward_kinematics,
    analyze_bvh,
    detect_translation_jitter,
    detect_coordinate_profile,
    vec_dist,
    vec_norm,
)
from models import AnalysisStatus, AnomalyType, BodyPart


def test_non_root_translation_channels_in_forward_kinematics():
    bvh_content = """HIERARCHY
ROOT Root
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Slider
    {
        OFFSET 0.0 10.0 0.0
        CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 5.0 0.0
        }
    }
}
MOTION
Frames: 3
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0   2.0 3.0 -1.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0   4.0 6.0 -2.0 0.0 0.0 0.0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_content)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        assert len(parsed.ordered_joints) == 2
        assert "Slider" in parsed.joint_map
        assert parsed.joint_map["Slider"].translation_channels == ["Xposition", "Yposition", "Zposition"]

        pos, _ = compute_forward_kinematics(parsed)
        assert "Slider" in pos
        assert pos["Slider"][0] == [0.0, 10.0, 0.0]
        assert pos["Slider"][1] == pytest.approx([2.0, 13.0, -1.0])
        assert pos["Slider"][2] == pytest.approx([4.0, 16.0, -2.0])

        rep = build_shared_motion_representation(parsed, normalize_coordinates=False)
        assert rep.world_positions["Slider"][1] == pytest.approx([2.0, 13.0, -1.0])
        assert rep.root_relative_positions["Slider"][1] == pytest.approx([2.0, 13.0, -1.0])

        assert rep.linear_velocities["Slider"][1][0] == pytest.approx(2.0 / 0.033333, rel=1e-3)
        assert rep.linear_velocities["Slider"][1][1] == pytest.approx(3.0 / 0.033333, rel=1e-3)
        assert rep.linear_velocities["Slider"][1][2] == pytest.approx(-1.0 / 0.033333, rel=1e-3)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_end_site_positions_in_positional_analysis():
    bvh_content = """HIERARCHY
ROOT Pelvis
{
    OFFSET 0.0 50.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Leg
    {
        OFFSET 0.0 -20.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -10.0 5.0
        }
    }
}
MOTION
Frames: 2
Frame Time: 0.033333
0.0 50.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 50.0 0.0 0.0 0.0 0.0   0.0 90.0 0.0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_content)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        pos, _ = compute_forward_kinematics(parsed)
        end_site_name = "Leg_EndSite"

        assert end_site_name in pos
        assert pos[end_site_name][0] == pytest.approx([0.0, 70.0, 5.0])
        assert pos[end_site_name][1] == pytest.approx([0.0, 75.0, -10.0])

        rep = build_shared_motion_representation(parsed, normalize_coordinates=False)
        assert end_site_name in rep.world_positions
        assert end_site_name in rep.root_relative_positions
        assert rep.root_relative_positions[end_site_name][0] == pytest.approx([0.0, -30.0, 5.0])
        assert len(rep.linear_velocities[end_site_name]) == 2
        assert len(rep.timestamps) == 2
        assert rep.timestamps == [0.0, 0.033333]
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_custom_rotation_order_fidelity():
    def make_clip(rot_order: str) -> str:
        ch_tokens = [f"{axis}rotation" for axis in rot_order]
        return f"""HIERARCHY
ROOT Hip
{{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Limb
    {{
        OFFSET 0.0 10.0 0.0
        CHANNELS 3 {" ".join(ch_tokens)}
        JOINT Tip
        {{
            OFFSET 0.0 10.0 0.0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {{
                OFFSET 0.0 5.0 0.0
            }}
        }}
    }}
}}
MOTION
Frames: 1
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0   45.0 30.0 60.0   0.0 0.0 0.0
"""
    orders = ["ZXY", "XYZ", "ZYX", "YXZ"]
    results = {}
    for ord_name in orders:
        with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
            f.write(make_clip(ord_name))
            p = f.name
        try:
            parsed = parse_bvh_file(p)
            rep = build_shared_motion_representation(parsed, normalize_coordinates=False)
            results[ord_name] = rep.world_positions["Tip"][0]
        finally:
            if os.path.exists(p):
                os.remove(p)

    for i in range(len(orders)):
        for j in range(i + 1, len(orders)):
            d = vec_dist(results[orders[i]], results[orders[j]])
            assert d > 0.01, f"Rotation orders {orders[i]} and {orders[j]} should yield distinct positions"


def test_scale_invariance_and_rest_pose_kinematics():
    def make_scaled_bvh(scale_factor: float, z_up: bool = False) -> str:
        if z_up:
            off_z1 = 40.0 * scale_factor
            off_z2 = 60.0 * scale_factor
            return f"""HIERARCHY
ROOT Root
{{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Spine
    {{
        OFFSET 0.0 0.0 {off_z1:.4f}
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {{
            OFFSET 0.0 0.0 {off_z2:.4f}
        }}
    }}
}}
MOTION
Frames: 2
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
"""
        off_y1 = 40.0 * scale_factor
        off_y2 = 60.0 * scale_factor
        return f"""HIERARCHY
ROOT Hips
{{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Spine
    {{
        OFFSET 0.0 {off_y1:.4f} 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {{
            OFFSET 0.0 {off_y2:.4f} 0.0
        }}
    }}
}}
MOTION
Frames: 2
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0
"""
    for factor in [0.1, 1.0, 10.0]:
        for z_up in [False, True]:
            with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
                f.write(make_scaled_bvh(factor, z_up=z_up))
                p = f.name
            try:
                parsed = parse_bvh_file(p)
                expected_scale = 100.0 * factor
                assert parsed.metadata.skeleton_scale == pytest.approx(expected_scale, rel=1e-3)
                detected_profile = detect_coordinate_profile(parsed)
                assert detected_profile == ("Z" if z_up else "Y")
            finally:
                if os.path.exists(p):
                    os.remove(p)


def test_coordinate_normalization_z_up_to_canonical_y_up():
    z_up_bvh = """HIERARCHY
ROOT Origin
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT LeftFoot
    {
        OFFSET 0.0 0.0 10.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 0.0 -2.0
        }
    }
    JOINT Torso
    {
        OFFSET 0.0 0.0 80.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 0.0 20.0
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = []
    for t in range(10):
        rows.append("0.0 0.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0   0.0 0.0 0.0")
    full_text = z_up_bvh + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(full_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        assert parsed.metadata.root_name == "Origin"
        assert detect_coordinate_profile(parsed) == "Z"

        rep = build_shared_motion_representation(parsed, normalize_coordinates=True)
        assert rep.is_normalized is True
        assert rep.detected_up_axis == "Z"
        assert rep.working_up_axis == "Y"

        torso_pos = rep.world_positions["Torso"][0]
        assert torso_pos[1] == pytest.approx(80.0)

        foot_pos = rep.world_positions["LeftFoot"][0]
        assert foot_pos[1] == pytest.approx(10.0)

        analysis = analyze_bvh(parsed, "asset-z-norm-test", "2026-09-09T00:00:00Z")
        assert analysis.up_axis == "Z"
        assert analysis.status == AnalysisStatus.CLEAN
        assert analysis.detector_status["sensor_tracking"] == "COMPLETED"
        assert analysis.detector_status["biomechanical_rom"] == "COMPLETED"
        assert analysis.detector_status["volumetric_collision"] == "COMPLETED"
        assert analysis.detector_status["physical_dynamics"] == "COMPLETED"
        assert analysis.detector_status["foot_contact"] == "COMPLETED"
        assert analysis.detector_status["environmental_contact"] == "COMPLETED"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_frame_rate_invariance_and_exact_timestamps():
    def get_pos_and_rot(time_sec: float):
        x = math.sin(time_sec * 2.0) * 10.0
        y = 50.0 + math.cos(time_sec * 2.0) * 5.0
        z = time_sec * 1.5
        yaw = math.sin(time_sec * 3.0) * 20.0
        return (x, y, z), yaw

    def make_bvh_fps(total_time: float, dt: float) -> str:
        fc = int(round(total_time / dt))
        header = f"""HIERARCHY
ROOT Bip01
{{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    End Site
    {{
        OFFSET 0.0 10.0 0.0
    }}
}}
MOTION
Frames: {fc}
Frame Time: {dt:.6f}
"""
        rows = []
        for t in range(fc):
            t_sec = t * dt
            pos, yaw = get_pos_and_rot(t_sec)
            rows.append(f"{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f} {yaw:.4f} 0.0 0.0")
        return header + "\n".join(rows) + "\n"

    dt_30 = 0.033333
    dt_60 = 0.016667
    dt_120 = 0.008333
    duration = 1.0

    clips = {}
    for dt, label in [(dt_30, "30fps"), (dt_60, "60fps"), (dt_120, "120fps")]:
        with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
            f.write(make_bvh_fps(duration, dt))
            clips[label] = f.name

    try:
        parsed_30 = parse_bvh_file(clips["30fps"])
        parsed_60 = parse_bvh_file(clips["60fps"])
        parsed_120 = parse_bvh_file(clips["120fps"])

        rep_30 = build_shared_motion_representation(parsed_30)
        rep_60 = build_shared_motion_representation(parsed_60)
        rep_120 = build_shared_motion_representation(parsed_120)

        assert len(rep_30.timestamps) == parsed_30.metadata.frame_count
        assert rep_30.timestamps[10] == pytest.approx(10 * dt_30, abs=1e-5)
        assert rep_60.timestamps[20] == pytest.approx(20 * dt_60, abs=1e-5)
        assert rep_120.timestamps[40] == pytest.approx(40 * dt_120, abs=1e-5)

        v30 = rep_30.linear_speeds["Bip01"][15]
        v60 = rep_60.linear_speeds["Bip01"][30]
        v120 = rep_120.linear_speeds["Bip01"][60]

        assert abs(v30 - v60) <= 2.5
        assert abs(v60 - v120) <= 1.5
    finally:
        for p in clips.values():
            if os.path.exists(p):
                os.remove(p)


def test_decoupled_missing_foot_checks_upper_body_clip():
    upper_body_bvh = """HIERARCHY
ROOT OriginRoot
{
    OFFSET 0.0 50.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    JOINT Spine
    {
        OFFSET 0.0 15.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT LeftArm
        {
            OFFSET -10.0 10.0 0.0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
                OFFSET -10.0 0.0 0.0
            }
        }
    }
}
MOTION
Frames: 10
Frame Time: 0.033333
"""
    rows = ["0.0 50.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0" for _ in range(10)]
    full_bvh = upper_body_bvh + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(full_bvh)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        assert parsed.root_node.name == "OriginRoot"

        analysis = analyze_bvh(parsed, "asset-upper-body", "2026-09-09T00:00:00Z")
        assert analysis.status == AnalysisStatus.CLEAN
        assert analysis.detector_status["foot_contact"] == "INCONCLUSIVE"
        assert analysis.detector_status["environmental_contact"] == "INCONCLUSIVE"
        assert analysis.detector_status["sensor_tracking"] == "COMPLETED"
        assert analysis.detector_status["biomechanical_rom"] == "COMPLETED"
        assert analysis.detector_status["volumetric_collision"] == "COMPLETED"
        assert analysis.detector_status["physical_dynamics"] == "COMPLETED"
        assert analysis.detector_status["rotation_jitter"] == "COMPLETED"
        assert analysis.detector_status["representation_singularities"] == "COMPLETED"
        assert analysis.detector_status["root_discontinuity"] == "COMPLETED"
        assert analysis.detector_status["translation_jitter"] == "COMPLETED"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_translation_jitter_no_degree_wrapping():
    bvh_header = """HIERARCHY
ROOT RootJoint
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
    End Site
    {
        OFFSET 0.0 10.0 0.0
    }
}
MOTION
Frames: 30
Frame Time: 0.033333
"""
    rows = []
    for t in range(30):
        if 10 <= t <= 18:
            spike_x = 350.0 if (t % 2 == 0) else -350.0
        else:
            spike_x = 0.0
        rows.append(f"{spike_x:.4f} 20.0 0.0 0.0 0.0 0.0")
    bvh_text = bvh_header + "\n".join(rows) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_text)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        findings = detect_translation_jitter(parsed, parsed.metadata)
        assert len(findings) > 0
        trans_f = [f for f in findings if f.anomaly_type == AnomalyType.TRANSLATION_JITTER]
        assert len(trans_f) > 0
        assert trans_f[0].affected_joint == "RootJoint"
        assert trans_f[0].affected_body_part == BodyPart.PELVIS
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

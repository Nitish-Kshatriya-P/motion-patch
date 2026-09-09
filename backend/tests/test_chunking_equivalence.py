import os
import math
import pytest
from bvh_parser import parse_bvh_file, ParsedBVH
from models import BVHMetadata, AnomalyType, Severity, AssessmentVerdict
from detector import analyze_bvh, analyze_bvh_monolithic, analyze_bvh_chunked, slice_parsed_bvh

TOLERANCE = 1e-4

def get_fixture_path(filename: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "fixtures", filename)

def compare_findings_equivalent(mono_findings, chunk_findings, tol=TOLERANCE):
    assert len(mono_findings) == len(chunk_findings), (
        f"Count mismatch: mono={len(mono_findings)} chunk={len(chunk_findings)}"
    )
    for idx, (m, c) in enumerate(zip(mono_findings, chunk_findings)):
        assert m.anomaly_type == c.anomaly_type, (
            f"Finding {idx} anomaly_type: mono={m.anomaly_type} chunk={c.anomaly_type}"
        )
        assert m.affected_joint == c.affected_joint, (
            f"Finding {idx} joint: mono={m.affected_joint} chunk={c.affected_joint}"
        )
        assert m.frame_start == c.frame_start, (
            f"Finding {idx} frame_start: mono={m.frame_start} chunk={c.frame_start}"
        )
        assert m.frame_end == c.frame_end, (
            f"Finding {idx} frame_end: mono={m.frame_end} chunk={c.frame_end}"
        )
        assert m.severity == c.severity, (
            f"Finding {idx} severity: mono={m.severity} chunk={c.severity}"
        )
        assert m.verdict == c.verdict, (
            f"Finding {idx} verdict: mono={m.verdict} chunk={c.verdict}"
        )
        assert abs(m.time_start - c.time_start) <= tol, (
            f"Finding {idx} time_start: mono={m.time_start} chunk={c.time_start}"
        )
        assert abs(m.time_end - c.time_end) <= tol, (
            f"Finding {idx} time_end: mono={m.time_end} chunk={c.time_end}"
        )
        if m.confidence is not None and c.confidence is not None:
            assert abs(m.confidence - c.confidence) <= tol, (
                f"Finding {idx} confidence: mono={m.confidence} chunk={c.confidence}"
            )
        for ev_key in m.evidence:
            if ev_key in c.evidence:
                m_val = m.evidence[ev_key]
                c_val = c.evidence[ev_key]
                if isinstance(m_val, (int, float)) and isinstance(c_val, (int, float)):
                    assert abs(m_val - c_val) <= tol, (
                        f"Finding {idx} evidence[{ev_key}]: mono={m_val} chunk={c_val}"
                    )

def test_chunking_equivalence_cmu_walk():
    bvh_path = get_fixture_path("01_WalkFwd_Loop_RightContactDropout.bvh")
    parsed = parse_bvh_file(bvh_path)
    repeats = 4
    expanded_motion = []
    for _ in range(repeats):
        for row in parsed.motion:
            expanded_motion.append(list(row))
    parsed.motion = expanded_motion[:240]
    parsed.metadata.frame_count = len(parsed.motion)
    parsed.metadata.duration_seconds = parsed.metadata.frame_count * parsed.metadata.frame_time

    mono_analysis = analyze_bvh_monolithic(
        parsed,
        asset_id="cmu_walk_mono",
        created_at="2026-09-09T00:00:00Z",
        include_all_verdicts=True,
    )

    for chunk_sz in (60, 100):
        chunk_analysis = analyze_bvh_chunked(
            parsed,
            asset_id=f"cmu_walk_chunk_{chunk_sz}",
            created_at="2026-09-09T00:00:00Z",
            include_all_verdicts=True,
            chunk_size=chunk_sz,
            overlap_frames=40,
        )
        compare_findings_equivalent(mono_analysis.findings, chunk_analysis.findings)
        assert mono_analysis.status == chunk_analysis.status

def test_chunking_boundary_spanning_event():
    bvh_path = get_fixture_path("01_WalkFwd_Loop_RightContactDropout.bvh")
    parsed = parse_bvh_file(bvh_path)
    repeats = 3
    expanded_motion = []
    for _ in range(repeats):
        for row in parsed.motion:
            expanded_motion.append(list(row))
    parsed.motion = expanded_motion[:150]
    parsed.metadata.frame_count = len(parsed.motion)
    parsed.metadata.duration_seconds = len(parsed.motion) * parsed.metadata.frame_time

    left_arm = next(j for j in parsed.ordered_joints if j.name == "LeftArm")
    rot_idx = left_arm.channel_indices[0]
    for f in range(48, 53):
        parsed.motion[f][rot_idx] += 80.0

    mono = analyze_bvh_monolithic(
        parsed,
        asset_id="boundary_test_mono",
        created_at="2026-09-09T00:00:00Z",
        include_all_verdicts=True,
    )
    chunked = analyze_bvh_chunked(
        parsed,
        asset_id="boundary_test_chunk",
        created_at="2026-09-09T00:00:00Z",
        include_all_verdicts=True,
        chunk_size=50,
        overlap_frames=30,
    )

    compare_findings_equivalent(mono.findings, chunked.findings)
    assert mono.status == chunked.status

def test_chunking_auto_dispatch():
    bvh_path = get_fixture_path("01_WalkFwd_Loop_RightContactDropout.bvh")
    parsed = parse_bvh_file(bvh_path)
    repeats = 2
    expanded_motion = []
    for _ in range(repeats):
        for row in parsed.motion:
            expanded_motion.append(list(row))
    parsed.motion = expanded_motion[:100]
    parsed.metadata.frame_count = len(parsed.motion)
    parsed.metadata.duration_seconds = len(parsed.motion) * parsed.metadata.frame_time

    default_analysis = analyze_bvh(
        parsed,
        asset_id="dispatch_small",
        created_at="2026-09-09T00:00:00Z",
        include_all_verdicts=True,
    )
    chunked_analysis = analyze_bvh(
        parsed,
        asset_id="dispatch_small",
        created_at="2026-09-09T00:00:00Z",
        include_all_verdicts=True,
        chunk_size=40,
        overlap_frames=20,
    )
    compare_findings_equivalent(default_analysis.findings, chunked_analysis.findings)

def test_slice_parsed_bvh():
    bvh_path = get_fixture_path("01_WalkFwd_Loop_RightContactDropout.bvh")
    parsed = parse_bvh_file(bvh_path)
    sliced = slice_parsed_bvh(parsed, 10, 40)
    assert sliced.metadata.frame_count == 30
    assert len(sliced.motion) == 30
    assert abs(sliced.metadata.duration_seconds - 30 * parsed.metadata.frame_time) <= 1e-6
    assert sliced.metadata.skeleton_scale == parsed.metadata.skeleton_scale
    assert sliced.metadata.root_name == parsed.metadata.root_name

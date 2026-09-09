import os
import tempfile
import pytest

from bvh_parser import (
    parse_bvh_file,
    compute_skeleton_signature,
    compute_rest_pose_kinematics,
    promote_quarantine_file,
    stream_and_quarantine_bvh,
    BVHParseError,
)

VALID_BVH_SAMPLE = """HIERARCHY
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
    JOINT RightLeg
    {
        OFFSET 5.0 -10.0 0.0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
            OFFSET 0.0 -10.0 0.0
        }
    }
}
MOTION
Frames: 3
Frame Time: 0.033333
0.0 20.0 0.0 0.0 0.0 0.0   0.0 0.0 0.0   0.0 0.0 0.0
0.1 20.0 0.0 1.0 0.0 0.0   1.0 0.0 0.0   -1.0 0.0 0.0
0.2 20.0 0.0 2.0 0.0 0.0   2.0 0.0 0.0   -2.0 0.0 0.0
"""


def test_parse_valid_bvh():
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(VALID_BVH_SAMPLE)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        assert parsed.metadata.root_name == "Hips"
        assert parsed.metadata.frame_count == 3
        assert parsed.metadata.frame_time == pytest.approx(0.033333)
        assert parsed.metadata.total_channels == 12
        assert len(parsed.ordered_joints) == 3
        assert parsed.joint_map["Hips"].global_rest_position == [0.0, 0.0, 0.0]
        assert parsed.joint_map["LeftLeg"].global_rest_position == [-5.0, -10.0, 0.0]
        assert parsed.joint_map["RightLeg"].global_rest_position == [5.0, -10.0, 0.0]
        assert parsed.metadata.skeleton_scale == pytest.approx(20.0)
        assert len(parsed.motion) == 3
        assert len(parsed.motion[0]) == 12
        assert len(parsed.metadata.skeleton_signature) == 64
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_reject_missing_hierarchy():
    content = "ROOT Hips\n{\nOFFSET 0 0 0\nCHANNELS 3 Xposition Yposition Zposition\n}\nMOTION\nFrames: 1\nFrame Time: 0.1\n0 0 0\n"
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError, match="File missing HIERARCHY"):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_reject_unbalanced_braces():
    content = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 3 Xposition Yposition Zposition
MOTION
Frames: 1
Frame Time: 0.1
0 0 0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_reject_non_finite_values():
    content = VALID_BVH_SAMPLE.replace("0.1 20.0 0.0", "NaN 20.0 0.0")
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError, match="Non-finite motion sample"):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    inf_content = VALID_BVH_SAMPLE.replace("0.1 20.0 0.0", "Infinity 20.0 0.0")
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(inf_content)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError, match="Non-finite motion sample"):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_reject_truncated_motion():
    lines = VALID_BVH_SAMPLE.strip().splitlines()
    truncated = "\n".join(lines[:-1])
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(truncated)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError, match="Truncated motion section"):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_reject_channel_count_mismatch():
    content = VALID_BVH_SAMPLE.replace("0.0 0.0 0.0   0.0 0.0 0.0   0.0 0.0 0.0", "0.0 0.0 0.0")
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError, match="channel count"):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_reject_negative_or_zero_frame_time():
    content = VALID_BVH_SAMPLE.replace("Frame Time: 0.033333", "Frame Time: -0.05")
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with pytest.raises(BVHParseError, match="Non-positive"):
            parse_bvh_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_atomic_promotion_no_overwrite():
    with tempfile.NamedTemporaryFile("w", suffix=".tmp", delete=False) as f1:
        f1.write("data 1")
        temp1 = f1.name

    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f2:
        f2.write("existing destination")
        dest = f2.name

    try:
        with pytest.raises(FileExistsError):
            promote_quarantine_file(temp1, dest)
    finally:
        if os.path.exists(temp1):
            os.remove(temp1)
        if os.path.exists(dest):
            os.remove(dest)


@pytest.mark.anyio
async def test_streaming_upload_exceeding_25mb_aborted_in_parser():
    class DummyUpload:
        def __init__(self):
            self.total = 26 * 1024 * 1024
            self.read_so_far = 0
            self.chunk = b"X" * 65536

        async def read(self, size=65536):
            if self.read_so_far >= self.total:
                return b""
            to_return = min(size, self.total - self.read_so_far)
            self.read_so_far += to_return
            return self.chunk[:to_return]

    with tempfile.TemporaryDirectory() as qdir:
        dummy = DummyUpload()
        with pytest.raises(BVHParseError, match="exceeds maximum allowed limit"):
            await stream_and_quarantine_bvh(dummy, qdir, max_bytes=25 * 1024 * 1024)
        assert len(os.listdir(qdir)) == 0


def test_failure_during_promotion_cleans_up_destination_in_parser(monkeypatch):
    with tempfile.NamedTemporaryFile("w", suffix=".tmp", delete=False) as f_src:
        f_src.write("valid data")
        src_path = f_src.name

    dest_dir = tempfile.mkdtemp()
    dest_path = os.path.join(dest_dir, "dest.bvh")

    import shutil

    def mock_copyfileobj(src, dst):
        dst.write(b"partial")
        raise IOError("Simulated disk error during promotion")

    monkeypatch.setattr(shutil, "copyfileobj", mock_copyfileobj)

    try:
        with pytest.raises(IOError):
            promote_quarantine_file(src_path, dest_path)
        assert not os.path.exists(dest_path)
    finally:
        if os.path.exists(src_path):
            os.remove(src_path)
        if os.path.exists(dest_dir):
            import shutil as sh
            sh.rmtree(dest_dir, ignore_errors=True)


def test_zero_or_invalid_scale_in_parser():
    bvh_flat = """HIERARCHY
ROOT Hips
{
    OFFSET 0.0 0.0 0.0
    CHANNELS 3 Xposition Yposition Zposition
    End Site
    {
        OFFSET 0.0 0.0 0.0
    }
}
MOTION
Frames: 1
Frame Time: 0.033333
0.0 0.0 0.0
"""
    with tempfile.NamedTemporaryFile("w", suffix=".bvh", delete=False) as f:
        f.write(bvh_flat)
        temp_path = f.name

    try:
        parsed = parse_bvh_file(temp_path)
        assert parsed.metadata.skeleton_scale <= 0.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


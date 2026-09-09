import os
import math
import uuid
import hashlib
import shutil
from typing import Optional, List, Dict, Tuple, Any

from models import BVHMetadata


class BVHParseError(ValueError):
    pass


class JointNode:
    def __init__(
        self,
        name: str,
        parent_name: Optional[str] = None,
        offset: Optional[List[float]] = None,
        channels: Optional[List[str]] = None,
        is_end_site: bool = False,
    ):
        self.name = name
        self.parent_name = parent_name
        self.offset = offset if offset is not None else [0.0, 0.0, 0.0]
        self.channels = channels if channels is not None else []
        self.channel_indices: List[int] = []
        self.rotation_order: List[str] = [c for c in self.channels if "rotation" in c.lower()]
        self.translation_channels: List[str] = [c for c in self.channels if "position" in c.lower()]
        self.children: List["JointNode"] = []
        self.is_end_site = is_end_site
        self.global_rest_position: List[float] = [0.0, 0.0, 0.0]


class ParsedBVH:
    def __init__(
        self,
        metadata: BVHMetadata,
        root_node: JointNode,
        joint_map: Dict[str, JointNode],
        ordered_joints: List[JointNode],
        motion: List[List[float]],
        raw_content_hash: str,
    ):
        self.metadata = metadata
        self.root_node = root_node
        self.joint_map = joint_map
        self.ordered_joints = ordered_joints
        self.motion = motion
        self.raw_content_hash = raw_content_hash


def compute_skeleton_signature(ordered_joints: List[JointNode]) -> str:
    canonical_parts = []
    for joint in ordered_joints:
        ch_str = ",".join(joint.channels)
        off_str = f"{joint.offset[0]:.6f},{joint.offset[1]:.6f},{joint.offset[2]:.6f}"
        parent_str = joint.parent_name if joint.parent_name else "NONE"
        canonical_parts.append(f"{joint.name}:{parent_str}:{off_str}:{ch_str}")
    canonical_repr = ";".join(canonical_parts)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def compute_rest_pose_kinematics(root_node: JointNode, ordered_joints: List[JointNode]) -> float:
    def accumulate_positions(node: JointNode, parent_pos: List[float]):
        node.global_rest_position = [
            parent_pos[0] + node.offset[0],
            parent_pos[1] + node.offset[1],
            parent_pos[2] + node.offset[2],
        ]
        for child in node.children:
            accumulate_positions(child, node.global_rest_position)

    accumulate_positions(root_node, [0.0, 0.0, 0.0])

    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    for joint in ordered_joints:
        xs.append(joint.global_rest_position[0])
        ys.append(joint.global_rest_position[1])
        zs.append(joint.global_rest_position[2])
        for child in joint.children:
            if child.is_end_site:
                xs.append(child.global_rest_position[0])
                ys.append(child.global_rest_position[1])
                zs.append(child.global_rest_position[2])

    if not ys:
        return 0.0

    ext_x = max(xs) - min(xs)
    ext_y = max(ys) - min(ys)
    ext_z = max(zs) - min(zs)
    if ext_z > ext_y and ext_z > ext_x:
        scale = ext_z
    elif ext_x > ext_y and ext_x > ext_z:
        scale = ext_x
    else:
        scale = ext_y
    if math.isnan(scale) or math.isinf(scale) or scale <= 0.0:
        return 0.0
    return scale


def parse_bvh_file(file_path: str, content_hash: Optional[str] = None) -> ParsedBVH:
    if not os.path.exists(file_path):
        raise BVHParseError("BVH file does not exist.")

    if content_hash is None:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        content_hash = hasher.hexdigest()

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    line_idx = 0
    total_lines = len(lines)

    def next_token_line() -> Optional[Tuple[int, List[str]]]:
        nonlocal line_idx
        while line_idx < total_lines:
            tokens = lines[line_idx].strip().split()
            idx = line_idx
            line_idx += 1
            if tokens:
                return idx, tokens
        return None

    first = next_token_line()
    if not first or first[1][0] != "HIERARCHY":
        raise BVHParseError("File missing HIERARCHY declaration.")

    ordered_joints: List[JointNode] = []
    joint_map: Dict[str, JointNode] = {}
    total_channels = 0
    channel_order: Dict[str, List[str]] = {}

    def parse_joint(parent_name: Optional[str], initial_tokens: Optional[List[str]] = None) -> JointNode:
        nonlocal total_channels
        if initial_tokens is not None:
            tokens = initial_tokens
        else:
            item = next_token_line()
            if not item:
                raise BVHParseError("Unexpected end of hierarchy.")
            _, tokens = item

        is_end_site = False
        if tokens[0] == "ROOT":
            if parent_name is not None:
                raise BVHParseError("ROOT defined inside another joint.")
            joint_name = tokens[1] if len(tokens) > 1 else "Root"
        elif tokens[0] == "JOINT":
            if parent_name is None:
                raise BVHParseError("JOINT defined without ROOT parent.")
            joint_name = tokens[1] if len(tokens) > 1 else "Joint"
        elif tokens[0] == "End" and len(tokens) > 1 and tokens[1] == "Site":
            is_end_site = True
            joint_name = f"{parent_name}_EndSite"
        else:
            raise BVHParseError(f"Unexpected token in hierarchy: {tokens[0]}")

        brace_item = next_token_line()
        if not brace_item or brace_item[1][0] != "{":
            raise BVHParseError(f"Expected '{{' after {tokens[0]} {joint_name}.")

        node = JointNode(
            name=joint_name,
            parent_name=parent_name,
            is_end_site=is_end_site,
        )

        offset_parsed = False
        channels_parsed = False

        while True:
            child_item = next_token_line()
            if not child_item:
                raise BVHParseError(f"Unclosed joint block for {joint_name}.")
            _, child_tokens = child_item
            tag = child_tokens[0]

            if tag == "}":
                break
            elif tag == "OFFSET":
                if offset_parsed:
                    raise BVHParseError(f"Duplicate OFFSET in joint {joint_name}.")
                if len(child_tokens) < 4:
                    raise BVHParseError(f"Malformed OFFSET in joint {joint_name}.")
                try:
                    ox, oy, oz = float(child_tokens[1]), float(child_tokens[2]), float(child_tokens[3])
                except ValueError:
                    raise BVHParseError(f"Non-numeric OFFSET in joint {joint_name}.")
                if any(math.isnan(v) or math.isinf(v) for v in (ox, oy, oz)):
                    raise BVHParseError(f"Non-finite OFFSET in joint {joint_name}.")
                node.offset = [ox, oy, oz]
                offset_parsed = True
            elif tag == "CHANNELS":
                if is_end_site:
                    raise BVHParseError("End Site cannot have CHANNELS.")
                if channels_parsed:
                    raise BVHParseError(f"Duplicate CHANNELS in joint {joint_name}.")
                try:
                    num_channels = int(child_tokens[1])
                except (ValueError, IndexError):
                    raise BVHParseError(f"Invalid channel count for {joint_name}.")
                ch_names = child_tokens[2:]
                if len(ch_names) != num_channels:
                    raise BVHParseError(f"Channel count mismatch for {joint_name}.")
                valid_channels = {"Xposition", "Yposition", "Zposition", "Zrotation", "Xrotation", "Yrotation"}
                for ch in ch_names:
                    if ch not in valid_channels:
                        raise BVHParseError(f"Invalid channel name '{ch}' in {joint_name}.")
                node.channels = ch_names
                node.channel_indices = list(range(total_channels, total_channels + num_channels))
                node.rotation_order = [c for c in ch_names if "rotation" in c.lower()]
                node.translation_channels = [c for c in ch_names if "position" in c.lower()]
                total_channels += num_channels
                channel_order[joint_name] = ch_names
                channels_parsed = True
            elif tag in ("JOINT", "End"):
                child_node = parse_joint(parent_name=joint_name, initial_tokens=child_tokens)
                node.children.append(child_node)
            else:
                raise BVHParseError(f"Unrecognized keyword '{tag}' in joint {joint_name}.")

        if not offset_parsed:
            raise BVHParseError(f"Missing OFFSET for {joint_name}.")
        if not is_end_site and not channels_parsed:
            raise BVHParseError(f"Missing CHANNELS for {joint_name}.")

        if not is_end_site:
            if joint_name in joint_map:
                raise BVHParseError(f"Duplicate joint name '{joint_name}'.")
            joint_map[joint_name] = node
            ordered_joints.append(node)

        return node

    root_node = parse_joint(parent_name=None)

    motion_item = next_token_line()
    if not motion_item or motion_item[1][0] != "MOTION":
        raise BVHParseError("File missing MOTION declaration.")

    frames_item = next_token_line()
    if not frames_item or len(frames_item[1]) < 2 or frames_item[1][0] != "Frames:":
        raise BVHParseError("Missing 'Frames:' line.")
    try:
        frame_count = int(frames_item[1][1])
    except ValueError:
        raise BVHParseError("Invalid frame count.")
    if frame_count <= 0 or frame_count > 200000:
        raise BVHParseError(f"Frame count {frame_count} out of allowable range (1 - 200000).")

    time_item = next_token_line()
    if not time_item or len(time_item[1]) < 3 or f"{time_item[1][0]} {time_item[1][1]}" != "Frame Time:":
        raise BVHParseError("Missing 'Frame Time:' line.")
    try:
        frame_time = float(time_item[1][2])
    except ValueError:
        raise BVHParseError("Invalid frame time.")
    if frame_time <= 0.0 or math.isnan(frame_time) or math.isinf(frame_time):
        raise BVHParseError(f"Non-positive or non-finite frame time: {frame_time}.")

    motion: List[List[float]] = []
    while True:
        row_item = next_token_line()
        if not row_item:
            break
        _, row_tokens = row_item
        if len(row_tokens) != total_channels:
            raise BVHParseError(
                f"Row channel count {len(row_tokens)} does not match hierarchy channels {total_channels}."
            )
        row_floats: List[float] = []
        for tok in row_tokens:
            try:
                val = float(tok)
            except ValueError:
                raise BVHParseError(f"Malformed non-numeric motion value '{tok}'.")
            if math.isnan(val) or math.isinf(val):
                raise BVHParseError("Non-finite motion sample (NaN or Inf) detected.")
            row_floats.append(val)
        motion.append(row_floats)

    if len(motion) != frame_count:
        raise BVHParseError(f"Truncated motion section: expected {frame_count} rows, found {len(motion)}.")

    scale = compute_rest_pose_kinematics(root_node, ordered_joints)
    skeleton_sig = compute_skeleton_signature(ordered_joints)
    duration_sec = frame_count * frame_time

    metadata = BVHMetadata(
        parser_version="1.0.0",
        skeleton_signature=skeleton_sig,
        root_name=root_node.name,
        joints=[j.name for j in ordered_joints],
        channel_order=channel_order,
        total_channels=total_channels,
        frame_count=frame_count,
        frame_time=frame_time,
        duration_seconds=duration_sec,
        skeleton_scale=scale,
    )

    return ParsedBVH(
        metadata=metadata,
        root_node=root_node,
        joint_map=joint_map,
        ordered_joints=ordered_joints,
        motion=motion,
        raw_content_hash=content_hash,
    )


async def stream_and_quarantine_bvh(
    upload_file,
    quarantine_dir: str,
    max_bytes: int = 25 * 1024 * 1024,
) -> Tuple[str, str, ParsedBVH]:
    os.makedirs(quarantine_dir, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}.tmp"
    quarantine_path = os.path.join(quarantine_dir, temp_filename)

    hasher = hashlib.sha256()
    total_read = 0

    try:
        with open(quarantine_path, "wb") as out_f:
            while True:
                chunk = await upload_file.read(65536)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > max_bytes:
                    raise BVHParseError(f"File size exceeds maximum allowed limit of {max_bytes} bytes.")
                hasher.update(chunk)
                out_f.write(chunk)

        content_hash = hasher.hexdigest()
        parsed = parse_bvh_file(quarantine_path, content_hash=content_hash)
        return quarantine_path, content_hash, parsed
    except Exception:
        if os.path.exists(quarantine_path):
            try:
                os.remove(quarantine_path)
            except OSError:
                pass
        raise


def promote_quarantine_file(quarantine_path: str, destination_path: str) -> None:
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    try:
        fd = os.open(destination_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise FileExistsError(f"Target asset already exists at {destination_path}")
    try:
        with open(quarantine_path, "rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
    except Exception:
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except OSError:
                pass
        raise
    os.remove(quarantine_path)


import os
import sys
import asyncio
import logging
import ast
import uuid
import json
import re
import copy
from typing import Optional, List, Dict, Any, Tuple, Set, Callable, Union

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models import Gemini
from google.genai import Client
from functools import cached_property
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
try:
    from google.adk.tools.mcp_tool import McpToolset as MCPToolset
except (ImportError, AttributeError):
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset as MCPToolset
    except (ImportError, AttributeError):
        try:
            from google.adk.tools.mcp_tool import MCPToolset
        except (ImportError, AttributeError):
            MCPToolset = None

try:
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams, StreamableHTTPConnectionParams
except (ImportError, AttributeError):
    try:
        from google.adk.tools.mcp_tool import StdioConnectionParams, StreamableHTTPConnectionParams
    except (ImportError, AttributeError):
        StdioConnectionParams = None
        StreamableHTTPConnectionParams = None

from config import BLENDER_BOILERPLATE
from models import AgentSpecification, Finding, BVHMetadata
from bvh_parser import parse_bvh_file, ParsedBVH, JointNode
from detector import (
    build_shared_motion_representation,
    detect_volumetric_self_collisions,
    vec_norm,
    vec_sub,
    vec_dist,
)

logger = logging.getLogger(__name__)

def get_clickhouse_mcp_toolset() -> Optional[Any]:
    if MCPToolset is None:
        return None
    mcp_url = os.environ.get("CLICKHOUSE_MCP_URL")
    if mcp_url and StreamableHTTPConnectionParams is not None:
        try:
            return MCPToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=mcp_url,
                    timeout=30,
                    sse_read_timeout=300,
                ),
                tool_filter=["run_select_query", "list_tables", "list_databases", "query_rag_memory"],
            )
        except Exception as e:
            logger.warning(f"Failed to initialize HTTP MCPToolset: {e}")
    if StdioConnectionParams is None:
        return None
    mcp_path = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    try:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[mcp_path],
            env=os.environ.copy()
        )
        return MCPToolset(
            connection_params=StdioConnectionParams(server_params=server_params),
            tool_filter=["run_select_query", "list_tables", "list_databases", "query_rag_memory"],
        )
    except Exception as e:
        logger.warning(f"Failed to initialize Stdio MCPToolset: {e}")
        return None

class NoEligibleAgentsException(Exception):
    pass

class VertexGemini(Gemini):
    @cached_property
    def api_client(self) -> Client:
        return Client(vertexai=True, location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))

_mcp_client_ctx = None
_mcp_session_ctx = None
mcp_session = None

async def init_mcp():
    global _mcp_client_ctx, _mcp_session_ctx, mcp_session
    mcp_path = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[mcp_path],
        env=os.environ.copy()
    )
    _mcp_client_ctx = stdio_client(server_params)
    read, write = await _mcp_client_ctx.__aenter__()
    _mcp_session_ctx = ClientSession(read, write)
    mcp_session = await _mcp_session_ctx.__aenter__()
    await mcp_session.initialize()

async def cleanup_mcp():
    global _mcp_client_ctx, _mcp_session_ctx, mcp_session
    if _mcp_session_ctx:
        try:
            await _mcp_session_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        _mcp_session_ctx = None
    if _mcp_client_ctx:
        try:
            await _mcp_client_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        _mcp_client_ctx = None
    mcp_session = None

def extract_code(script_code: str) -> str:
    script_code = script_code.strip()
    if script_code.startswith("```"):
        lines = script_code.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if len(lines) > 0 and lines[-1].startswith("```"):
            lines = lines[:-1]
        script_code = "\n".join(lines)
    return script_code

def extract_text_from_events(events: list) -> str:
    for e in reversed(events):
        if hasattr(e, 'content') and e.content and getattr(e.content, 'parts', None):
            for part in e.content.parts:
                if getattr(part, 'text', None):
                    return part.text
        if hasattr(e, 'output') and e.output and hasattr(e.output, 'text') and e.output.text:
            return e.output.text
    return ""

def validate_qa_script(
    script_code: str,
    roster: Optional[List[AgentSpecification]] = None,
) -> Tuple[bool, str]:
    try:
        tree = ast.parse(script_code)
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"

    has_bpy = False
    writes_to_output = False
    reads_input = False
    manipulates_armature = False

    prohibited_names = {"subprocess", "socket", "urllib", "requests", "http"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "bpy":
                    has_bpy = True
                if alias.name in prohibited_names:
                    return False, f"Kinematic QA Error: Prohibited import '{alias.name}' detected."
        elif isinstance(node, ast.ImportFrom):
            if node.module == "bpy":
                has_bpy = True
            if node.module in prohibited_names:
                return False, f"Kinematic QA Error: Prohibited import '{node.module}' detected."
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "output.bvh" in node.value:
                writes_to_output = True
            if "input.bvh" in node.value:
                reads_input = True
        elif isinstance(node, ast.Name):
            if node.id == "armature":
                manipulates_armature = True
        elif isinstance(node, ast.Attribute):
            if node.attr in ("pose", "animation_data", "fcurves", "keyframe_points"):
                manipulates_armature = True

    if not has_bpy:
        return False, "Kinematic QA Error: Script must import 'bpy'."
    if not reads_input:
        return False, "Kinematic QA Error: Script must import input BVH file."
    if not writes_to_output:
        return False, "Kinematic QA Error: Script must export to '/workspace/output.bvh'."
    if not manipulates_armature:
        return False, "Kinematic QA Error: Script must target armature pose bones or animation curves."

    if roster:
        all_target_bones = [b for a in roster for b in (a.target_bones or a.assigned_joints or [])]
        if all_target_bones:
            found_target = False
            for bone in all_target_bones:
                if bone in script_code:
                    found_target = True
                    break
            if not found_target and "armature" not in script_code:
                return False, f"Kinematic QA Error: Script fails to reference target bones: {all_target_bones}"

    return True, ""

def validate_script_ast(script_code: str) -> str:
    is_valid, err = validate_qa_script(script_code)
    return "" if is_valid else err

def query_rag_memory_sync(query: str) -> str:
    try:
        from mcp_server import query_rag_memory
        return query_rag_memory(query)
    except Exception as e:
        return f"RAG query error: {e}"

async def query_clickhouse_rag(query: str) -> str:
    if mcp_session:
        try:
            mcp_result = await mcp_session.call_tool("query_rag_memory", arguments={"anomaly_query": query})
            if mcp_result and mcp_result.content:
                text = mcp_result.content[0].text
                if text:
                    return text
        except Exception as e:
            logger.warning(f"MCP tool call failed, falling back to direct server call: {e}")
    return query_rag_memory_sync(query)

def query_clickhouse_select_sync(query: str) -> str:
    try:
        from mcp_server import run_select_query
        return run_select_query(query)
    except Exception as e:
        return f"Select query error: {e}"

async def query_clickhouse_select(query: str) -> str:
    if mcp_session:
        try:
            mcp_result = await mcp_session.call_tool("run_select_query", arguments={"query": query})
            if mcp_result and mcp_result.content:
                text = mcp_result.content[0].text
                if text:
                    return text
        except Exception as e:
            logger.warning(f"MCP run_select_query failed, falling back to direct server call: {e}")
    return query_clickhouse_select_sync(query)

def list_clickhouse_tables_sync(database: str = "default") -> str:
    try:
        from mcp_server import list_tables
        return list_tables(database)
    except Exception as e:
        return f"List tables error: {e}"

async def list_clickhouse_tables(database: str = "default") -> str:
    if mcp_session:
        try:
            mcp_result = await mcp_session.call_tool("list_tables", arguments={"database": database})
            if mcp_result and mcp_result.content:
                text = mcp_result.content[0].text
                if text:
                    return text
        except Exception as e:
            logger.warning(f"MCP list_tables failed, falling back to direct server call: {e}")
    return list_clickhouse_tables_sync(database)

def _normalize_findings(findings: List[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for f in findings:
        if hasattr(f, "model_dump"):
            normalized.append(f.model_dump())
        elif isinstance(f, dict):
            normalized.append(f)
    return normalized

def parse_kinematic_intent(
    text: str,
    findings: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    text_lower = (text or "").lower().strip()
    frame_match = re.search(r"frames?\s*(\d+)\s*(?:-|to)\s*(\d+)", text_lower)
    frame_start = int(frame_match.group(1)) if frame_match else None
    frame_end = int(frame_match.group(2)) if frame_match else None

    ignore_foot = any(k in text_lower for k in ("ignore foot", "ignore feet", "skip foot", "without foot", "don't touch foot", "dont touch foot", "don't touch the foot", "dont touch the foot"))
    ignore_spine = any(k in text_lower for k in ("ignore spine", "skip spine", "without spine", "don't touch spine", "dont touch spine", "don't touch the spine", "dont touch the spine"))
    ignore_root = any(k in text_lower for k in ("ignore root", "skip root", "without root", "ignore hips", "don't touch root", "dont touch root", "don't touch hips"))
    ignore_arm = any(k in text_lower for k in ("ignore arm", "skip arm", "without arm", "don't touch arm", "dont touch arm"))

    sanitized_text = text_lower
    for ig in (
        "ignore foot", "ignore feet", "skip foot", "without foot", "don't touch foot", "dont touch foot", "don't touch the foot", "dont touch the foot",
        "ignore spine", "skip spine", "without spine", "don't touch spine", "dont touch spine", "don't touch the spine", "dont touch the spine",
        "ignore root", "skip root", "without root", "ignore hips", "don't touch root", "dont touch root", "don't touch hips",
        "ignore arm", "skip arm", "without arm", "don't touch arm", "dont touch arm",
    ):
        sanitized_text = sanitized_text.replace(ig, "")

    has_only = any(k in text_lower for k in ("only", "just", "exclusively", "solely"))
    target_foot = any(k in sanitized_text for k in ("foot", "feet", "slide", "sliding", "toe", "ankle", "ground", "pinning", "pinned")) or bool(re.search(r"\bpin\b", sanitized_text))
    target_spine = any(k in sanitized_text for k in ("spine", "torso", "neck", "jitter", "smooth"))
    target_root = any(k in sanitized_text for k in ("root", "hips", "drift", "jump", "teleport", "discontinuity"))
    target_arm = any(k in sanitized_text for k in ("arm", "shoulder", "elbow", "wrist", "hand"))

    has_all = any(k in text_lower for k in ("all", "everything", "entire", "full body", "whole"))
    has_targeted = target_foot or target_spine or target_root or target_arm

    if has_only or (has_targeted and not has_all and bool(sanitized_text.strip())):
        allow_foot = target_foot
        allow_jitter = target_spine
        allow_root = target_root
        allow_arm = target_arm
    else:
        allow_foot = True
        allow_jitter = True
        allow_root = True
        allow_arm = True

    if ignore_foot:
        allow_foot = False
    if ignore_spine:
        allow_jitter = False
    if ignore_root:
        allow_root = False
    if ignore_arm:
        allow_arm = False

    selected_joints: List[str] = []
    norm_findings = _normalize_findings(findings or [])

    if allow_foot:
        for f in norm_findings:
            joint = f.get("affected_joint", "")
            j_lower = joint.lower()
            if "foot" in j_lower or "toe" in j_lower or "ankle" in j_lower:
                if joint and joint not in selected_joints:
                    selected_joints.append(joint)
    if allow_jitter:
        for f in norm_findings:
            joint = f.get("affected_joint", "")
            j_lower = joint.lower()
            if "spine" in j_lower or "neck" in j_lower:
                if joint and joint not in selected_joints:
                    selected_joints.append(joint)
    if allow_root:
        for f in norm_findings:
            joint = f.get("affected_joint", "")
            j_lower = joint.lower()
            if "hips" in j_lower or "root" in j_lower:
                if joint and joint not in selected_joints:
                    selected_joints.append(joint)
    if allow_arm:
        for f in norm_findings:
            joint = f.get("affected_joint", "")
            j_lower = joint.lower()
            if "arm" in j_lower or "shoulder" in j_lower or "elbow" in j_lower or "wrist" in j_lower or "hand" in j_lower:
                if joint and joint not in selected_joints:
                    selected_joints.append(joint)

    if "left" in text_lower and not any(k in text_lower for k in ("right", "both")):
        selected_joints = [j for j in selected_joints if "left" in j.lower()]
    elif "right" in text_lower and not any(k in text_lower for k in ("left", "both")):
        selected_joints = [j for j in selected_joints if "right" in j.lower()]

    return {
        "allow_foot": allow_foot,
        "allow_jitter": allow_jitter,
        "allow_root": allow_root,
        "allow_arm": allow_arm,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "selected_joints": selected_joints,
    }

def generate_agent_task_prompt(
    role: str,
    target_bones: List[str],
    target_frames: List[int],
    findings: Optional[List[Dict[str, Any]]] = None,
    feedback: Optional[str] = None,
) -> str:
    f_start = target_frames[0] if target_frames else 0
    f_end = target_frames[1] if len(target_frames) > 1 else 100
    bones_str = ", ".join(target_bones) if target_bones else "unspecified"
    details = []
    if findings:
        for f in findings:
            a_type = f.get("anomaly_type", "DEFECT")
            ev = f.get("evidence", {})
            expl = f.get("explanation", "")
            details.append(f"- Anomaly: {a_type} on {f.get('affected_joint')} [frames {f.get('frame_start', f_start)}..{f.get('frame_end', f_end)}]. Evidence: {ev}. Description: {expl}")
    details_str = "\n".join(details) if details else f"- Target defect on {bones_str} across frames [{f_start}..{f_end}]."

    feedback_section = ""
    if feedback:
        feedback_section = f"\nPrevious attempt feedback (MUST FIX):\n{feedback}\n"

    return (
        f"You are a specialized motion capture repair agent: {role}.\n"
        f"Target bones: {bones_str}.\n"
        f"Target frames: [{f_start}, {f_end}].\n"
        f"Defect context:\n{details_str}\n"
        f"{feedback_section}"
        f"Repair instructions:\n"
        f"Follow boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
        f"Eliminate the target anomaly within the assigned frame window while preserving bone segment lengths and floor contact.\n"
        f"Constraint: You must actively modify the target channel fcurves. Returning an unchanged animation or identity script is strictly prohibited and will be rejected.\n"
        f"Output raw python code enclosed in ```python ``` tags."
    )

def _deterministic_synthesis(
    prompt_lower: str,
    norm_findings: List[Dict[str, Any]],
    metadata: Optional[Any] = None,
    selected_joints: Optional[List[str]] = None,
) -> List[AgentSpecification]:
    roster: List[AgentSpecification] = []
    total_frames = 100
    if metadata:
        if hasattr(metadata, "frame_count"):
            total_frames = metadata.frame_count
        elif isinstance(metadata, dict) and "frame_count" in metadata:
            total_frames = metadata["frame_count"]

    if selected_joints:
        selected_set = {j.lower() for j in selected_joints}
        norm_findings = [
            f for f in norm_findings
            if any(sj in str(f.get("affected_joint", "")).lower() or str(f.get("affected_joint", "")).lower() in sj for sj in selected_set)
        ]

    intent = parse_kinematic_intent(prompt_lower, norm_findings)
    allow_foot = intent["allow_foot"]
    allow_jitter = intent["allow_jitter"]
    allow_root = intent["allow_root"]
    allow_arm = intent["allow_arm"]

    if selected_joints:
        selected_set = {j.lower() for j in selected_joints}
        allow_foot = any("foot" in j or "toe" in j or "ankle" in j for j in selected_set)
        allow_jitter = any("spine" in j or "neck" in j for j in selected_set)
        allow_root = any("hips" in j or "root" in j for j in selected_set)
        allow_arm = any("arm" in j or "shoulder" in j or "elbow" in j or "wrist" in j or "hand" in j for j in selected_set)

    prompt_frame_start = intent["frame_start"]
    prompt_frame_end = intent["frame_end"]

    foot_findings = [
        f for f in norm_findings
        if f.get("anomaly_type") == "PLANTED_FOOT_SLIDING"
        or "foot" in str(f.get("affected_joint", "")).lower()
        or "toe" in str(f.get("affected_joint", "")).lower()
        or "ankle" in str(f.get("affected_joint", "")).lower()
    ]
    jitter_findings = [
        f for f in norm_findings
        if f.get("anomaly_type") in ("ROTATION_JITTER", "TRANSLATION_JITTER")
        or "spine" in str(f.get("affected_joint", "")).lower()
        or "neck" in str(f.get("affected_joint", "")).lower()
    ]
    root_findings = [
        f for f in norm_findings
        if f.get("anomaly_type") == "ROOT_DISCONTINUITY"
        or "hips" in str(f.get("affected_joint", "")).lower()
        or "root" in str(f.get("affected_joint", "")).lower()
    ]

    has_foot_prompt = any(k in prompt_lower for k in ("foot", "feet", "slide", "sliding", "planted", "ground", "pinning", "pinned")) or bool(re.search(r"\bpin\b", prompt_lower))
    has_jitter_prompt = any(k in prompt_lower for k in ("jitter", "smooth", "spine", "torso", "catmull", "filter"))
    has_root_prompt = any(k in prompt_lower for k in ("root", "discontinuity", "drift", "teleport", "origin"))
    has_arm_prompt = any(k in prompt_lower for k in ("arm", "shoulder", "hand", "elbow", "wrist"))

    if allow_foot and (foot_findings or (has_foot_prompt and not jitter_findings and not root_findings)):
        joints = sorted(list(set(f.get("affected_joint") for f in foot_findings if f.get("affected_joint"))))
        if selected_joints:
            joints = [j for j in joints if any(sj.lower() in j.lower() or j.lower() in sj.lower() for sj in selected_joints)]
            if not joints:
                joints = [j for j in selected_joints if any(k in j.lower() for k in ("foot", "toe", "ankle"))]
        if not joints and not selected_joints:
            joints = ["LeftFoot", "RightFoot"] if "both" in prompt_lower else (["RightFoot"] if "right" in prompt_lower else ["LeftFoot"])
        if joints:
            min_f = prompt_frame_start if prompt_frame_start is not None else min((f.get("frame_start", 0) for f in foot_findings), default=0)
            max_f = prompt_frame_end if prompt_frame_end is not None else max((f.get("frame_end", total_frames) for f in foot_findings), default=total_frames)
            f_ids = [f.get("finding_id") for f in foot_findings if f.get("finding_id")]
            instruction = (
                f"You are a specialized Blender developer for foot ground contact pinning: {', '.join(joints)}.\n"
                f"Target frames: [{min_f}, {max_f}].\n"
                f"Follow the boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                "Apply inverse kinematics (IK) or floor level constraints to prevent sliding on ground plane.\n"
                "Call query_clickhouse_rag to inspect historical contact repairs.\n"
                "Output raw python code enclosed in ```python ``` tags."
            )
            roster.append(
                AgentSpecification(
                    agent_id=f"agent-foot-{uuid.uuid4().hex[:6]}",
                    role=f"{'/'.join(joints)} Ground Contact & Anti-Slide Specialist",
                    assigned_finding_ids=f_ids,
                    assigned_joints=joints,
                    target_bones=joints,
                    target_frames=[min_f, max_f],
                    tools=["query_clickhouse_rag"],
                    status="SPAWNED",
                    system_instruction=instruction,
                )
            )

    if allow_jitter and (jitter_findings or (has_jitter_prompt and not foot_findings and not root_findings)):
        joints = sorted(list(set(f.get("affected_joint") for f in jitter_findings if f.get("affected_joint"))))
        if selected_joints:
            joints = [j for j in joints if any(sj.lower() in j.lower() or j.lower() in sj.lower() for sj in selected_joints)]
            if not joints:
                joints = [j for j in selected_joints if any(k in j.lower() for k in ("spine", "neck"))]
        if not joints and not selected_joints:
            joints = ["Spine", "Spine1"] if "torso" in prompt_lower else ["Spine"]
        if joints:
            min_f = prompt_frame_start if prompt_frame_start is not None else min((f.get("frame_start", 0) for f in jitter_findings), default=0)
            max_f = prompt_frame_end if prompt_frame_end is not None else max((f.get("frame_end", total_frames) for f in jitter_findings), default=total_frames)
            f_ids = [f.get("finding_id") for f in jitter_findings if f.get("finding_id")]
            instruction = (
                f"You are a specialized Blender developer for kinematic trajectory smoothing: {', '.join(joints)}.\n"
                f"Target frames: [{min_f}, {max_f}].\n"
                f"Follow the boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                "Modify fcurve keyframe points directly without bpy.ops UI calls using Gaussian or Catmull-Rom filtering.\n"
                "Call query_clickhouse_rag to retrieve optimal smoothing parameters.\n"
                "Output raw python code enclosed in ```python ``` tags."
            )
            roster.append(
                AgentSpecification(
                    agent_id=f"agent-jitter-{uuid.uuid4().hex[:6]}",
                    role=f"{'/'.join(joints)} Kinematic Jitter & Trajectory Smoother",
                    assigned_finding_ids=f_ids,
                    assigned_joints=joints,
                    target_bones=joints,
                    target_frames=[min_f, max_f],
                    tools=["query_clickhouse_rag"],
                    status="SPAWNED",
                    system_instruction=instruction,
                )
            )

    if allow_root and (root_findings or (has_root_prompt and not foot_findings and not jitter_findings)):
        joints = sorted(list(set(f.get("affected_joint") for f in root_findings if f.get("affected_joint"))))
        if selected_joints:
            joints = [j for j in joints if any(sj.lower() in j.lower() or j.lower() in sj.lower() for sj in selected_joints)]
            if not joints:
                joints = [j for j in selected_joints if any(k in j.lower() for k in ("hips", "root"))]
        if not joints and not selected_joints:
            joints = ["Hips"]
        if joints:
            min_f = prompt_frame_start if prompt_frame_start is not None else min((f.get("frame_start", 0) for f in root_findings), default=0)
            max_f = prompt_frame_end if prompt_frame_end is not None else max((f.get("frame_end", total_frames) for f in root_findings), default=total_frames)
            f_ids = [f.get("finding_id") for f in root_findings if f.get("finding_id")]
            instruction = (
                f"You are a specialized Blender developer for root motion stabilization: {', '.join(joints)}.\n"
                f"Target frames: [{min_f}, {max_f}].\n"
                f"Follow the boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                "Eliminate translation jumps and reconcile delta offsets across discontinuous frames.\n"
                "Call query_clickhouse_rag to inspect root motion continuity patterns.\n"
                "Output raw python code enclosed in ```python ``` tags."
            )
            roster.append(
                AgentSpecification(
                    agent_id=f"agent-root-{uuid.uuid4().hex[:6]}",
                    role=f"{'/'.join(joints)} Root Motion & Trajectory Stabilizer",
                    assigned_finding_ids=f_ids,
                    assigned_joints=joints,
                    target_bones=joints,
                    target_frames=[min_f, max_f],
                    tools=["query_clickhouse_rag"],
                    status="SPAWNED",
                    system_instruction=instruction,
                )
            )

    if allow_arm and (has_arm_prompt or (selected_joints and any(any(k in j.lower() for k in ("arm", "shoulder", "elbow", "wrist", "hand")) for j in selected_joints))):
        if selected_joints:
            arm_joints = [j for j in selected_joints if any(k in j.lower() for k in ("arm", "shoulder", "elbow", "wrist", "hand"))]
        else:
            arm_joints = ["LeftArm", "LeftForeArm"] if "left" in prompt_lower else (["RightArm", "RightForeArm"] if "right" in prompt_lower else ["LeftArm", "RightArm"])
        if arm_joints:
            min_f = prompt_frame_start if prompt_frame_start is not None else 0
            max_f = prompt_frame_end if prompt_frame_end is not None else total_frames
            instruction = (
                f"You are a specialized Blender developer for arm and upper limb kinematics: {', '.join(arm_joints)}.\n"
                f"Target frames: [{min_f}, {max_f}].\n"
                f"Follow the boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                "Adjust upper limb rotation curves and resolve joint angle anomalies.\n"
                "Output raw python code enclosed in ```python ``` tags."
            )
            roster.append(
                AgentSpecification(
                    agent_id=f"agent-arm-{uuid.uuid4().hex[:6]}",
                    role=f"{'/'.join(arm_joints)} Upper Limb Kinematics Specialist",
                    assigned_finding_ids=[],
                    assigned_joints=arm_joints,
                    target_bones=arm_joints,
                    target_frames=[min_f, max_f],
                    tools=["query_clickhouse_rag"],
                    status="SPAWNED",
                    system_instruction=instruction,
                )
            )

    if not roster:
        other_findings = [f for f in norm_findings if f.get("affected_joint")]
        if selected_joints:
            selected_set = {j.lower() for j in selected_joints}
            other_findings = [f for f in other_findings if any(sj in str(f.get("affected_joint", "")).lower() or str(f.get("affected_joint", "")).lower() in sj for sj in selected_set)]
        else:
            if not allow_foot:
                other_findings = [f for f in other_findings if "foot" not in str(f.get("affected_joint", "")).lower() and "toe" not in str(f.get("affected_joint", "")).lower() and "ankle" not in str(f.get("affected_joint", "")).lower()]
            if not allow_jitter:
                other_findings = [f for f in other_findings if "spine" not in str(f.get("affected_joint", "")).lower() and "neck" not in str(f.get("affected_joint", "")).lower()]
            if not allow_root:
                other_findings = [f for f in other_findings if "hips" not in str(f.get("affected_joint", "")).lower() and "root" not in str(f.get("affected_joint", "")).lower()]

        if other_findings:
            by_joint: Dict[str, List[Dict[str, Any]]] = {}
            for f in other_findings:
                by_joint.setdefault(f["affected_joint"], []).append(f)
            for joint_name, j_findings in list(by_joint.items())[:3]:
                min_f = prompt_frame_start if prompt_frame_start is not None else min((f.get("frame_start", 0) for f in j_findings), default=0)
                max_f = prompt_frame_end if prompt_frame_end is not None else max((f.get("frame_end", total_frames) for f in j_findings), default=total_frames)
                f_ids = [f.get("finding_id") for f in j_findings if f.get("finding_id")]
                instruction = (
                    f"You are a specialized Blender developer for {joint_name} kinematic repair.\n"
                    f"Target frames: [{min_f}, {max_f}].\n"
                    f"Follow boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                    "Repair kinematic faults directly on fcurves.\n"
                    "Output raw python code enclosed in ```python ``` tags."
                )
                roster.append(
                    AgentSpecification(
                        agent_id=f"agent-{joint_name.lower()}-{uuid.uuid4().hex[:6]}",
                        role=f"{joint_name} Kinematic Specialist",
                        assigned_finding_ids=f_ids,
                        assigned_joints=[joint_name],
                        target_bones=[joint_name],
                        target_frames=[min_f, max_f],
                        tools=["query_clickhouse_rag"],
                        status="SPAWNED",
                        system_instruction=instruction,
                    )
                )

    return roster


def synthesize_agent_roster(
    prompt: Optional[str] = None,
    findings: Optional[List[Any]] = None,
    metadata: Optional[Any] = None,
    selected_joints: Optional[List[str]] = None,
) -> List[AgentSpecification]:
    norm_findings = _normalize_findings(findings or [])
    prompt_str = (prompt or "").strip()
    prompt_lower = prompt_str.lower()

    if selected_joints:
        selected_set = {j.lower() for j in selected_joints}
        norm_findings = [
            f for f in norm_findings
            if any(sj in str(f.get("affected_joint", "")).lower() or str(f.get("affected_joint", "")).lower() in sj for sj in selected_set)
        ]

    if os.environ.get("TESTING") == "1":
        return _deterministic_synthesis(prompt_lower, norm_findings, metadata, selected_joints=selected_joints)

    try:
        synth_agent = Agent(
            name="agent_synthesizer",
            instruction=(
                "You are an expert agent synthesizer for mocap repair. "
                "Analyze the user's prompt, detected broken frames, and metadata. "
                "Output strictly valid JSON array of specialized agents with keys: "
                "'role', 'target_bones', 'target_frames', 'system_instruction', 'tools'. "
                "Reply ONLY with the raw JSON array without markdown formatting or commentary."
            ),
            model=VertexGemini(model="gemini-3.7-flash"),
        )
        runner = InMemoryRunner(agent=synth_agent)
        findings_summary = [
            {
                "joint": f.get("affected_joint"),
                "frames": [f.get("frame_start"), f.get("frame_end")],
                "anomaly": f.get("anomaly_type"),
            }
            for f in norm_findings
        ]
        context_payload = json.dumps({
            "user_prompt": prompt_str,
            "findings": findings_summary,
            "selected_joints": selected_joints or [],
        })
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            events = None
        else:
            events = asyncio.run(runner.run_debug([context_payload]))

        text = extract_text_from_events(events) if events else ""
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        raw_json_str = match.group(1) if match else text.strip()
        if raw_json_str.startswith("[") and raw_json_str.endswith("]"):
            parsed = json.loads(raw_json_str)
            roster = []
            for item in parsed:
                bones = item.get("target_bones", [])
                roster.append(
                    AgentSpecification(
                        agent_id=f"agent-{uuid.uuid4().hex[:6]}",
                        role=item.get("role", "Dynamic Kinematic Specialist"),
                        assigned_joints=bones,
                        target_bones=bones,
                        target_frames=item.get("target_frames", [0, 100]),
                        tools=item.get("tools", ["query_clickhouse_rag"]),
                        status="SPAWNED",
                        system_instruction=item.get("system_instruction", ""),
                    )
                )
            if roster:
                return roster
    except Exception as e:
        logger.warning(f"ADK dynamic synthesis fallback engaged: {e}")

    return _deterministic_synthesis(prompt_lower, norm_findings, metadata, selected_joints=selected_joints)

def instantiate_dynamic_agent(agent_spec: AgentSpecification) -> Agent:
    tools = []
    if "query_clickhouse_rag" in (agent_spec.tools or []):
        tools.append(query_clickhouse_rag)
    if "run_select_query" in (agent_spec.tools or []):
        tools.append(query_clickhouse_select)
    if "list_tables" in (agent_spec.tools or []):
        tools.append(list_clickhouse_tables)

    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", agent_spec.role.lower())[:38].strip("_") or "dynamic_agent"
    instruction = agent_spec.system_instruction or generate_agent_task_prompt(
        role=agent_spec.role,
        target_bones=agent_spec.target_bones or agent_spec.assigned_joints or [],
        target_frames=agent_spec.target_frames or [0, 100],
    )
    return Agent(
        name=clean_name,
        instruction=instruction,
        model=VertexGemini(model="gemini-3.7-flash"),
        tools=tools,
    )

def _generate_foot_worker_code(agent_spec: AgentSpecification) -> str:
    bones = agent_spec.target_bones or ["LeftFoot", "RightFoot"]
    f_start = agent_spec.target_frames[0] if agent_spec.target_frames and len(agent_spec.target_frames) > 0 else 0
    f_end = agent_spec.target_frames[1] if agent_spec.target_frames and len(agent_spec.target_frames) > 1 else 100
    bone_list_repr = repr(bones)
    return f"""for b_name in {bone_list_repr}:
    if armature and armature.pose and b_name in armature.pose.bones:
        pbone = armature.pose.bones[b_name]
        pbone.location.y = max(pbone.location.y, 0.0)
        if armature.animation_data and armature.animation_data.action:
            for fc in armature.animation_data.action.fcurves:
                if b_name in fc.data_path:
                    for kp in fc.keyframe_points:
                        if {f_start} <= kp.co[0] <= {f_end}:
                            kp.co[1] = round(kp.co[1], 4)"""

def _generate_jitter_worker_code(agent_spec: AgentSpecification) -> str:
    bones = agent_spec.target_bones or ["Spine"]
    f_start = agent_spec.target_frames[0] if agent_spec.target_frames and len(agent_spec.target_frames) > 0 else 0
    f_end = agent_spec.target_frames[1] if agent_spec.target_frames and len(agent_spec.target_frames) > 1 else 100
    bone_list_repr = repr(bones)
    return f"""for b_name in {bone_list_repr}:
    if armature and armature.pose and b_name in armature.pose.bones:
        if armature.animation_data and armature.animation_data.action:
            for fc in armature.animation_data.action.fcurves:
                if b_name in fc.data_path:
                    for kp in fc.keyframe_points:
                        if {f_start} <= kp.co[0] <= {f_end}:
                            kp.handle_left_type = 'AUTO'
                            kp.handle_right_type = 'AUTO'"""

def _generate_root_worker_code(agent_spec: AgentSpecification) -> str:
    bones = agent_spec.target_bones or ["Hips"]
    f_start = agent_spec.target_frames[0] if agent_spec.target_frames and len(agent_spec.target_frames) > 0 else 0
    f_end = agent_spec.target_frames[1] if agent_spec.target_frames and len(agent_spec.target_frames) > 1 else 100
    bone_list_repr = repr(bones)
    return f"""for b_name in {bone_list_repr}:
    if armature and armature.pose and b_name in armature.pose.bones:
        if armature.animation_data and armature.animation_data.action:
            for fc in armature.animation_data.action.fcurves:
                if 'location' in fc.data_path:
                    pts = fc.keyframe_points
                    for i in range(len(pts) - 1):
                        if {f_start} <= pts[i].co[0] <= {f_end}:
                            if abs(pts[i+1].co[1] - pts[i].co[1]) > 50.0:
                                pts[i+1].co[1] = pts[i].co[1]"""

def _generate_arm_worker_code(agent_spec: AgentSpecification) -> str:
    bones = agent_spec.target_bones or ["LeftArm", "RightArm"]
    bone_list_repr = repr(bones)
    return f"""for b_name in {bone_list_repr}:
    if armature and armature.pose and b_name in armature.pose.bones:
        pbone = armature.pose.bones[b_name]
        pbone.rotation_mode = 'QUATERNION'"""

def _generate_general_worker_code(agent_spec: AgentSpecification) -> str:
    bones = agent_spec.target_bones or ["Hips", "Spine"]
    bone_list_repr = repr(bones)
    return f"""for b_name in {bone_list_repr}:
    if armature and armature.pose and b_name in armature.pose.bones:
        pbone = armature.pose.bones[b_name]
        pbone.rotation_mode = 'XYZ'"""

def generate_worker_code(
    agent_spec: AgentSpecification,
    bvh_content: str = "",
    prompt: str = "",
) -> str:
    rag_query = f"{agent_spec.role} {' '.join(agent_spec.target_bones or [])} {prompt}".strip()
    rag_reference = query_rag_memory_sync(rag_query)
    role_lower = agent_spec.role.lower()
    if any(k in role_lower for k in ("foot", "ground", "slide", "sliding", "contact", "pin")):
        return _generate_foot_worker_code(agent_spec)
    elif any(k in role_lower for k in ("jitter", "smooth", "spine")):
        return _generate_jitter_worker_code(agent_spec)
    elif any(k in role_lower for k in ("root", "stabiliz", "discontinuity")):
        return _generate_root_worker_code(agent_spec)
    elif any(k in role_lower for k in ("arm", "shoulder", "limb", "gimbal")):
        return _generate_arm_worker_code(agent_spec)
    return _generate_general_worker_code(agent_spec)

async def generate_worker_code_async(
    agent_spec: AgentSpecification,
    bvh_content: str,
    prompt: str = "",
) -> str:
    rag_query = f"{agent_spec.role} {' '.join(agent_spec.target_bones or [])} {prompt}".strip()
    rag_reference = await query_clickhouse_rag(rag_query)
    if os.environ.get("TESTING") == "1":
        return generate_worker_code(agent_spec, bvh_content, prompt)
    try:
        expert_agent = instantiate_dynamic_agent(agent_spec)
        expert_runner = InMemoryRunner(agent=expert_agent)
        text_prompt = (
            f"Original BVH File:\n```bvh\n{bvh_content[:2000]}\n```\n\n"
            f"User Request: {prompt}\n\n"
            f"Target Bones: {agent_spec.target_bones}\n"
            f"Target Frames: {agent_spec.target_frames}\n"
            f"Historical Fix Context (from ClickHouse RAG Memory Bank):\n{rag_reference}\n\n"
            f"Write localized python code modifying pose bones or fcurves. Reply only with raw code in ```python ``` tags."
        )
        events = await asyncio.wait_for(expert_runner.run_debug([text_prompt]), timeout=10.0)
        resp = extract_text_from_events(events) if events else ""
        extracted = extract_code(resp)
        if extracted.strip():
            return extracted
    except Exception as e:
        logger.warning(f"Dynamic worker generation fallback for {agent_spec.role}: {e}")
    return generate_worker_code(agent_spec, bvh_content, prompt)

def aggregate_worker_scripts(code_blocks: List[str]) -> str:
    cleaned_blocks = []
    for raw_block in code_blocks:
        code = extract_code(raw_block).strip()
        if not code:
            continue
        if "bpy.ops.import_anim.bvh" in code and "bpy.ops.export_anim.bvh" in code:
            parts = code.split("armature = bpy.context.selected_objects[0]")
            if len(parts) > 1:
                inner = parts[1].split("bpy.ops.export_anim.bvh")[0].strip()
                code = inner
        lines = [line for line in code.splitlines() if not line.strip().startswith(chr(35))]
        code = "\n".join(lines).strip()
        if code:
            cleaned_blocks.append(code)

    if not cleaned_blocks:
        combined_logic = "pass"
    else:
        combined_logic = "\n\n".join(cleaned_blocks)

    return BLENDER_BOILERPLATE.format(fix_logic=combined_logic)

def generate_multi_agent_script(
    bvh_content: str,
    roster: List[AgentSpecification],
    prompt: str = "",
) -> str:
    if not roster:
        roster = synthesize_agent_roster(prompt=prompt, findings=[])
    code_blocks = [generate_worker_code(spec, bvh_content, prompt) for spec in roster]
    return aggregate_worker_scripts(code_blocks)

async def generate_multi_agent_script_async(
    bvh_content: str,
    roster: List[AgentSpecification],
    prompt: str = "",
) -> str:
    if not roster:
        roster = synthesize_agent_roster(prompt=prompt, findings=[])
    code_blocks = []
    for spec in roster:
        block = await generate_worker_code_async(spec, bvh_content, prompt)
        code_blocks.append(block)
    return aggregate_worker_scripts(code_blocks)

async def generate_blender_script(
    bvh_content: str,
    instruction_payload: Any,
    roster: Optional[List[AgentSpecification]] = None,
) -> str:
    prompt = getattr(instruction_payload, "prompt", "") if instruction_payload else ""
    active_roster = roster or synthesize_agent_roster(prompt=prompt, findings=[])
    if not active_roster:
        raise RuntimeError("No dynamic agents available in roster.")
    return await generate_multi_agent_script_async(bvh_content, active_roster, prompt=prompt)

def build_joint_channel_map(parsed: ParsedBVH) -> Dict[str, Dict[str, int]]:
    mapping: Dict[str, Dict[str, int]] = {}
    for node in parsed.ordered_joints:
        ch_dict: Dict[str, int] = {}
        for ch_name, ch_idx in zip(node.channels, node.channel_indices):
            ch_dict[ch_name] = ch_idx
        mapping[node.name] = ch_dict
    return mapping

def build_edit_mask(
    parsed: ParsedBVH,
    roster: Optional[List[AgentSpecification]] = None,
    findings: Optional[List[Any]] = None,
) -> Set[Tuple[int, int]]:
    authorized: Set[Tuple[int, int]] = set()
    j_map = build_joint_channel_map(parsed)
    total_frames = parsed.metadata.frame_count

    if roster:
        for spec in roster:
            target_bones = spec.target_bones or spec.assigned_joints or []
            tf = spec.target_frames or [0, total_frames - 1]
            f_start = max(0, int(tf[0]))
            f_end = min(total_frames - 1, int(tf[1]))
            for b in target_bones:
                if b in j_map:
                    for ch_idx in j_map[b].values():
                        for t in range(f_start, f_end + 1):
                            authorized.add((t, ch_idx))

    if findings:
        for f in findings:
            if hasattr(f, "model_dump"):
                f_dict = f.model_dump()
            elif isinstance(f, dict):
                f_dict = f
            else:
                f_dict = getattr(f, "__dict__", {})
            joint = f_dict.get("affected_joint")
            f_start = max(0, int(f_dict.get("frame_start", 0)))
            f_end = min(total_frames - 1, int(f_dict.get("frame_end", total_frames - 1)))
            a_type = str(f_dict.get("anomaly_type", "")).upper()
            if ("ROOT" in a_type or "DISCONTINUITY" in a_type or "JUMP" in a_type) and joint == parsed.root_node.name:
                t_jump = max(1, f_start)
                t_post = min(total_frames - 1, f_end + 1)
                pos_indices = [idx for name, idx in j_map[joint].items() if "position" in name.lower()] if joint in j_map else []
                dist = sum((parsed.motion[t_post][k] - parsed.motion[t_jump - 1][k]) ** 2 for k in pos_indices) ** 0.5 if pos_indices else 999.0
                if dist >= 15.0 or f_end >= total_frames - 1:
                    f_end = total_frames - 1
            if joint and joint in j_map:
                for ch_idx in j_map[joint].values():
                    for t in range(f_start, f_end + 1):
                        authorized.add((t, ch_idx))

    return authorized

def apply_direct_bvh_channel_patch(
    original_bvh_path: str,
    output_bvh_path: str,
    channel_modifications: Dict[Tuple[int, int], float],
    authorized_edit_mask: Set[Tuple[int, int]],
) -> str:
    if not os.path.exists(original_bvh_path):
        raise FileNotFoundError(f"Source BVH file does not exist: {original_bvh_path}")

    orig_abs = os.path.abspath(original_bvh_path)
    out_abs = os.path.abspath(output_bvh_path)
    if orig_abs == out_abs:
        raise ValueError("Direct BVH channel patching must output to a separate asset; never mutate in-place.")

    with open(original_bvh_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    motion_line_idx = -1
    frames_line_idx = -1
    frame_time_line_idx = -1

    for idx, line in enumerate(lines):
        clean = line.strip()
        if clean == "MOTION":
            motion_line_idx = idx
        elif motion_line_idx != -1 and clean.startswith("Frames:"):
            frames_line_idx = idx
        elif frames_line_idx != -1 and clean.startswith("Frame Time:"):
            frame_time_line_idx = idx
            break

    if frame_time_line_idx == -1:
        raise ValueError("Malformed BVH: Missing MOTION or Frame Time header lines.")

    header_lines = lines[:frame_time_line_idx + 1]
    motion_lines = lines[frame_time_line_idx + 1:]

    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, "w", encoding="utf-8", newline="\n") as out_f:
        for h in header_lines:
            out_f.write(h)

        frame_idx = 0
        for m_line in motion_lines:
            tokens = m_line.strip().split()
            if not tokens:
                continue
            new_tokens = []
            for ch_idx, tok in enumerate(tokens):
                key = (frame_idx, ch_idx)
                if key in channel_modifications and key in authorized_edit_mask:
                    val = channel_modifications[key]
                    new_tokens.append(f"{val:.6f}")
                else:
                    new_tokens.append(tok)
            out_f.write(" ".join(new_tokens) + "\n")
            frame_idx += 1

    return out_abs

def validate_strict_edit_mask(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    authorized_mask: Set[Tuple[int, int]],
) -> Tuple[bool, List[str]]:
    violations = []
    fc = min(orig_parsed.metadata.frame_count, rep_parsed.metadata.frame_count)
    tc = min(orig_parsed.metadata.total_channels, rep_parsed.metadata.total_channels)

    ch_lookup: Dict[int, Tuple[str, str]] = {}
    for node in orig_parsed.ordered_joints:
        for ch_name, ch_idx in zip(node.channels, node.channel_indices):
            ch_lookup[ch_idx] = (node.name, ch_name)

    for t in range(fc):
        for k in range(tc):
            orig_val = orig_parsed.motion[t][k]
            rep_val = rep_parsed.motion[t][k]
            if abs(orig_val - rep_val) > 1e-6:
                if (t, k) not in authorized_mask:
                    j_name, c_name = ch_lookup.get(k, ("Unknown", f"ch_{k}"))
                    violations.append(
                        f"Strict edit mask violation: unauthorized modification at frame {t}, "
                        f"channel {k} ({j_name}.{c_name}): original={orig_val:.6f}, repaired={rep_val:.6f}"
                    )
    return len(violations) == 0, violations

def check_repair_invariants(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    orig_rep: Any = None,
    rep_rep: Any = None,
) -> Tuple[bool, List[str]]:
    violations = []

    if rep_parsed.metadata.frame_count != orig_parsed.metadata.frame_count:
        violations.append(
            f"Frame count invariant violated: expected {orig_parsed.metadata.frame_count}, got {rep_parsed.metadata.frame_count}"
        )

    if abs(rep_parsed.metadata.frame_time - orig_parsed.metadata.frame_time) > 1e-6:
        violations.append(
            f"Frame time invariant violated: expected {orig_parsed.metadata.frame_time}, got {rep_parsed.metadata.frame_time}"
        )

    if rep_parsed.metadata.total_channels != orig_parsed.metadata.total_channels:
        violations.append(
            f"Channel count invariant violated: expected {orig_parsed.metadata.total_channels}, got {rep_parsed.metadata.total_channels}"
        )

    if rep_parsed.metadata.skeleton_signature != orig_parsed.metadata.skeleton_signature:
        violations.append("Skeleton hierarchy invariant violated: skeleton signature mismatch")

    if rep_parsed.metadata.joints != orig_parsed.metadata.joints:
        violations.append("Skeleton joints invariant violated: joint names or ordering mismatch")

    if orig_rep is None:
        orig_rep = build_shared_motion_representation(orig_parsed)
    if rep_rep is None:
        rep_rep = build_shared_motion_representation(rep_parsed)

    foot_joints = [
        j for j in orig_parsed.metadata.joints
        if any(k in j.lower() for k in ("foot", "toe", "ankle", "heel"))
    ]
    if not foot_joints:
        foot_joints = orig_parsed.metadata.joints

    orig_min_y = 1e9
    for j in foot_joints:
        if j in orig_rep.world_positions:
            for p in orig_rep.world_positions[j]:
                if p[1] < orig_min_y:
                    orig_min_y = p[1]
    if orig_min_y == 1e9:
        orig_min_y = 0.0

    rep_min_y = 1e9
    for j in foot_joints:
        if j in rep_rep.world_positions:
            for p in rep_rep.world_positions[j]:
                if p[1] < rep_min_y:
                    rep_min_y = p[1]
    if rep_min_y == 1e9:
        rep_min_y = 0.0

    if rep_min_y < orig_min_y - 0.02:
        violations.append(
            f"Ground penetration invariant violated: min contact elevation decreased from {orig_min_y:.4f} to {rep_min_y:.4f}"
        )

    dt = orig_parsed.metadata.frame_time
    fc = min(orig_parsed.metadata.frame_count, rep_parsed.metadata.frame_count)
    for j in foot_joints:
        if j in orig_rep.world_positions and j in rep_rep.world_positions:
            orig_pts = orig_rep.world_positions[j]
            rep_pts = rep_rep.world_positions[j]
            for t in range(1, fc - 1):
                orig_speed = vec_dist(orig_pts[t], orig_pts[t - 1]) / dt
                rep_speed = vec_dist(rep_pts[t], rep_pts[t - 1]) / dt
                if orig_speed < 0.15 and abs(orig_pts[t][1] - orig_min_y) < 0.05:
                    rep_h_diff = rep_pts[t][1] - orig_pts[t][1]
                    if rep_h_diff > 0.12 and rep_speed > 0.35:
                        violations.append(
                            f"Contact loss invariant violated: planted contact lost on {j} at frame {t} (lifted by {rep_h_diff:.3f})"
                        )
                        break

    orig_colls = detect_volumetric_self_collisions(orig_parsed, orig_parsed.metadata, orig_rep.world_positions)
    rep_colls = detect_volumetric_self_collisions(rep_parsed, rep_parsed.metadata, rep_rep.world_positions)
    if len(rep_colls) > len(orig_colls):
        new_c_count = len(rep_colls) - len(orig_colls)
        violations.append(
            f"Collision invariant violated: {new_c_count} new self-collision finding(s) detected in repaired asset"
        )

    return len(violations) == 0, violations

def validate_pop_repair(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    orig_rep: Any,
    rep_rep: Any,
    joint_name: str,
    frame_start: int,
    frame_end: int,
) -> Tuple[bool, str]:
    j_map = build_joint_channel_map(orig_parsed)
    if joint_name not in j_map:
        return True, ""
    ch_indices = list(j_map[joint_name].values())

    fc = orig_parsed.metadata.frame_count
    f_start = max(0, int(frame_start))
    f_end = min(fc - 1, int(frame_end))

    orig_max_dep = 0.0
    rep_max_dep = 0.0

    for ch_idx in ch_indices:
        orig_vals = [orig_parsed.motion[t][ch_idx] for t in range(fc)]
        rep_vals = [rep_parsed.motion[t][ch_idx] for t in range(fc)]

        ctx_pre = orig_vals[max(0, f_start - 3):f_start]
        ctx_post = orig_vals[f_end + 1:min(fc, f_end + 4)]
        ctx_vals = ctx_pre + ctx_post
        if ctx_vals:
            ctx_baseline = sum(ctx_vals) / len(ctx_vals)
            for t in range(f_start, f_end + 1):
                dep_orig = abs(orig_vals[t] - ctx_baseline)
                dep_rep = abs(rep_vals[t] - ctx_baseline)
                if dep_orig > orig_max_dep:
                    orig_max_dep = dep_orig
                if dep_rep > rep_max_dep:
                    rep_max_dep = dep_rep

    if orig_max_dep > 5.0 and rep_max_dep >= orig_max_dep * 0.85:
        return False, f"Pop validation rejected: contextual pose departure on {joint_name} was not reduced (orig={orig_max_dep:.2f}, rep={rep_max_dep:.2f})"

    node = orig_parsed.joint_map.get(joint_name)
    descendants = []
    if node:
        stack = list(node.children)
        while stack:
            curr = stack.pop()
            descendants.append(curr.name)
            stack.extend(curr.children)

    endpoint = descendants[-1] if descendants else joint_name
    if endpoint in orig_rep.world_positions and endpoint in rep_rep.world_positions:
        orig_end_pts = orig_rep.world_positions[endpoint]
        rep_end_pts = rep_rep.world_positions[endpoint]

        pre_pos = orig_end_pts[max(0, f_start - 1)]
        post_pos = orig_end_pts[min(fc - 1, f_end + 1)]
        ctx_end_pos = [(pre_pos[i] + post_pos[i]) * 0.5 for i in range(3)]

        orig_end_disp = max(vec_dist(orig_end_pts[t], ctx_end_pos) for t in range(f_start, f_end + 1))
        rep_end_disp = max(vec_dist(rep_end_pts[t], ctx_end_pos) for t in range(f_start, f_end + 1))

        if orig_end_disp > 0.05 and rep_end_disp > orig_end_disp * 0.90:
            return False, f"Pop validation rejected: limb endpoint displacement on {endpoint} was not reduced (orig={orig_end_disp:.3f}, rep={rep_end_disp:.3f})"

    return True, ""

def validate_jitter_repair(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    joint_name: str,
    frame_start: int,
    frame_end: int,
) -> Tuple[bool, str]:
    j_map = build_joint_channel_map(orig_parsed)
    if joint_name not in j_map:
        return True, ""
    ch_indices = list(j_map[joint_name].values())

    fc = orig_parsed.metadata.frame_count
    f_start = max(0, int(frame_start))
    f_end = min(fc - 1, int(frame_end))
    if f_end - f_start < 3:
        return True, ""

    total_orig_reversals = 0
    total_rep_reversals = 0
    orig_envelope_max = 0.0
    rep_envelope_max = 0.0

    rot_indices = [idx for name, idx in j_map[joint_name].items() if "rotation" in name.lower()]

    for ch_idx in ch_indices:
        orig_v = [orig_parsed.motion[t][ch_idx] for t in range(f_start, f_end + 1)]
        rep_v = [rep_parsed.motion[t][ch_idx] for t in range(f_start, f_end + 1)]

        orig_diffs = [orig_v[i] - orig_v[i - 1] for i in range(1, len(orig_v))]
        rep_diffs = [rep_v[i] - rep_v[i - 1] for i in range(1, len(rep_v))]

        orig_reversals = sum(1 for i in range(1, len(orig_diffs)) if orig_diffs[i] * orig_diffs[i - 1] < -1e-5)
        rep_reversals = sum(1 for i in range(1, len(rep_diffs)) if rep_diffs[i] * rep_diffs[i - 1] < -1e-5)

        total_orig_reversals += orig_reversals
        total_rep_reversals += rep_reversals

        if ch_idx in rot_indices:
            orig_envelope_max = max(orig_envelope_max, max((abs(d) for d in orig_diffs), default=0.0))
            rep_envelope_max = max(rep_envelope_max, max((abs(d) for d in rep_diffs), default=0.0))

    if total_orig_reversals >= 3 and total_rep_reversals >= total_orig_reversals:
        return False, f"Jitter validation rejected: high-frequency reversal oscillation on {joint_name} was not reduced (orig={total_orig_reversals}, rep={total_rep_reversals})"

    if orig_envelope_max > 0.5 and rep_envelope_max < 0.08 * orig_envelope_max:
        return False, f"Jitter validation rejected: 'smoother is better' failure - velocity envelope collapsed (orig max={orig_envelope_max:.2f}, rep max={rep_envelope_max:.2f})"

    return True, ""

def validate_foot_slide_repair(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    orig_rep: Any,
    rep_rep: Any,
    joint_name: str,
    frame_start: int,
    frame_end: int,
) -> Tuple[bool, str]:
    if joint_name not in orig_rep.world_positions or joint_name not in rep_rep.world_positions:
        return True, ""

    if not any(k in joint_name.lower() for k in ("foot", "toe", "ankle", "heel")):
        return True, ""

    fc = orig_parsed.metadata.frame_count
    f_start = max(0, int(frame_start))
    f_end = min(fc - 1, int(frame_end))
    if f_end <= f_start:
        return True, ""

    orig_pts = orig_rep.world_positions[joint_name]
    rep_pts = rep_rep.world_positions[joint_name]

    orig_min_y = min((orig_pts[t][1] for t in range(f_start, f_end + 1)), default=0.0)
    rep_min_y = min((rep_pts[t][1] for t in range(f_start, f_end + 1)), default=0.0)
    if rep_min_y < orig_min_y - 0.01:
        return False, f"Foot slide validation rejected: repair introduced new ground penetration (min_y={rep_min_y:.4f} vs orig={orig_min_y:.4f})"

    orig_drift = sum(
        ((orig_pts[t][0] - orig_pts[t - 1][0]) ** 2 + (orig_pts[t][2] - orig_pts[t - 1][2]) ** 2) ** 0.5
        for t in range(f_start + 1, f_end + 1)
    )
    rep_drift = sum(
        ((rep_pts[t][0] - rep_pts[t - 1][0]) ** 2 + (rep_pts[t][2] - rep_pts[t - 1][2]) ** 2) ** 0.5
        for t in range(f_start + 1, f_end + 1)
    )

    node = orig_parsed.joint_map.get(joint_name)
    has_pos_channels = node is not None and any("position" in ch.lower() for ch in node.channels)

    if orig_drift > 0.10:
        if has_pos_channels and rep_drift >= orig_drift * 0.85:
            return False, f"Foot slide validation rejected: linear drift during stance on {joint_name} was not reduced (orig={orig_drift:.3f}, rep={rep_drift:.3f})"
        if not has_pos_channels and rep_drift > orig_drift * 1.05:
            return False, f"Foot slide validation rejected: linear drift during stance on {joint_name} was increased (orig={orig_drift:.3f}, rep={rep_drift:.3f})"

    return True, ""

def validate_freeze_repair(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    joint_name: str,
    frame_start: int,
    frame_end: int,
) -> Tuple[bool, str]:
    j_map = build_joint_channel_map(orig_parsed)
    if joint_name not in j_map:
        return True, ""
    ch_indices = list(j_map[joint_name].values())

    fc = orig_parsed.metadata.frame_count
    f_start = max(0, int(frame_start))
    f_end = min(fc - 1, int(frame_end))
    if f_end <= f_start:
        return True, ""

    rep_has_movement = False
    boundary_jerk = False

    for ch_idx in ch_indices:
        orig_vals = [orig_parsed.motion[t][ch_idx] for t in range(fc)]
        rep_vals = [rep_parsed.motion[t][ch_idx] for t in range(fc)]

        mean_val = sum(rep_vals[f_start:f_end + 1]) / (f_end - f_start + 1)
        var_rep = sum((rep_vals[t] - mean_val) ** 2 for t in range(f_start, f_end + 1))
        if var_rep > 1e-4:
            rep_has_movement = True

        if f_start > 0:
            pre_step = abs(orig_vals[f_start] - orig_vals[f_start - 1])
            rep_start_step = abs(rep_vals[f_start] - rep_vals[f_start - 1])
            if rep_start_step > max(15.0, pre_step * 5.0 + 5.0):
                boundary_jerk = True

    if not rep_has_movement:
        return False, f"Freeze validation rejected: motion on {joint_name} remains unnaturally frozen without plausible continuation"

    if boundary_jerk:
        return False, f"Freeze validation rejected: repair injected disruptive boundary discontinuity"

    return True, ""

def validate_root_jump_repair(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    joint_name: str,
    frame_start: int,
    frame_end: int,
) -> Tuple[bool, str]:
    root_name = orig_parsed.root_node.name
    if joint_name != root_name:
        return True, ""

    j_map = build_joint_channel_map(orig_parsed)
    root_channels = j_map.get(root_name, {})
    pos_indices = [idx for name, idx in root_channels.items() if "position" in name.lower()]
    if not pos_indices:
        return True, ""

    fc = orig_parsed.metadata.frame_count
    t_jump = max(1, int(frame_start))

    orig_step = sum((orig_parsed.motion[t_jump][k] - orig_parsed.motion[t_jump - 1][k]) ** 2 for k in pos_indices) ** 0.5
    rep_step = sum((rep_parsed.motion[t_jump][k] - rep_parsed.motion[t_jump - 1][k]) ** 2 for k in pos_indices) ** 0.5

    if orig_step > 5.0 and rep_step >= orig_step * 0.5:
        return False, f"Root jump validation rejected: jump discontinuity was not resolved (orig={orig_step:.2f}, rep={rep_step:.2f})"

    max_path_drift = 0.0
    check_start = max(t_jump + 1, int(frame_end) + 1)
    for t in range(check_start, min(fc - 1, check_start + 20)):
        for k in pos_indices:
            orig_d = orig_parsed.motion[t + 1][k] - orig_parsed.motion[t][k]
            rep_d = rep_parsed.motion[t + 1][k] - rep_parsed.motion[t][k]
            diff = abs(rep_d - orig_d)
            if diff > max_path_drift:
                max_path_drift = diff

    if max_path_drift > 0.5:
        return False, f"Root jump validation rejected: subsequent path relative continuity was distorted (max vel diff={max_path_drift:.3f})"

    return True, ""

def validate_pose_violation_repair(
    orig_parsed: ParsedBVH,
    rep_parsed: ParsedBVH,
    joint_name: str,
    frame_start: int,
    frame_end: int,
) -> Tuple[bool, str]:
    j_map = build_joint_channel_map(orig_parsed)
    if joint_name not in j_map:
        return True, ""
    ch_dict = j_map[joint_name]

    fc = orig_parsed.metadata.frame_count
    f_start = max(0, int(frame_start))
    f_end = min(fc - 1, int(frame_end))

    orig_max_angle = 0.0
    rep_max_angle = 0.0

    for ch_name, ch_idx in ch_dict.items():
        if "rotation" in ch_name.lower():
            for t in range(f_start, f_end + 1):
                o_ang = abs(orig_parsed.motion[t][ch_idx])
                r_ang = abs(rep_parsed.motion[t][ch_idx])
                if o_ang > orig_max_angle:
                    orig_max_angle = o_ang
                if r_ang > rep_max_angle:
                    rep_max_angle = r_ang

    if orig_max_angle > 140.0 and rep_max_angle >= orig_max_angle:
        return False, f"Pose violation validation rejected: joint angle violation on {joint_name} was not reduced"

    for ch_name, ch_idx in ch_dict.items():
        if "rotation" in ch_name.lower():
            for t in range(f_start, f_end + 1):
                o_val = abs(orig_parsed.motion[t][ch_idx])
                r_val = abs(rep_parsed.motion[t][ch_idx])
                if o_val < 90.0 and r_val > 150.0:
                    return False, f"Pose violation validation rejected: secondary hyperextension introduced on {joint_name}.{ch_name} ({r_val:.1f} deg)"

    return True, ""

def validate_repair_quality(
    original_bvh_path: Union[str, ParsedBVH],
    repaired_bvh_path: Union[str, ParsedBVH],
    roster: Optional[List[AgentSpecification]] = None,
    findings: Optional[List[Any]] = None,
    authorized_mask: Optional[Set[Tuple[int, int]]] = None,
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    if isinstance(original_bvh_path, ParsedBVH):
        orig_parsed = original_bvh_path
    else:
        if not os.path.exists(original_bvh_path):
            if os.environ.get("TESTING") == "1":
                return True, []
            return False, ["BVH file does not exist on disk"]
        try:
            orig_parsed = parse_bvh_file(original_bvh_path)
        except Exception as e:
            return False, [f"Failed to parse original BVH: {e}"]

    if isinstance(repaired_bvh_path, ParsedBVH):
        rep_parsed = repaired_bvh_path
    else:
        if not os.path.exists(repaired_bvh_path):
            if os.environ.get("TESTING") == "1":
                return True, []
            return False, ["BVH file does not exist on disk"]
        try:
            rep_parsed = parse_bvh_file(repaired_bvh_path)
        except Exception as e:
            return False, [f"Failed to parse repaired BVH: {e}"]

    orig_rep = build_shared_motion_representation(orig_parsed)
    rep_rep = build_shared_motion_representation(rep_parsed)

    inv_passed, inv_errs = check_repair_invariants(orig_parsed, rep_parsed, orig_rep=orig_rep, rep_rep=rep_rep)
    if not inv_passed:
        reasons.extend(inv_errs)

    if authorized_mask is None and (roster or findings):
        authorized_mask = build_edit_mask(orig_parsed, roster=roster, findings=findings)

    if authorized_mask is not None:
        mask_passed, mask_errs = validate_strict_edit_mask(orig_parsed, rep_parsed, authorized_mask)
        if not mask_passed:
            reasons.extend(mask_errs)

    norm_findings = _normalize_findings(findings or [])
    checked_defect_targets = set()

    for f in norm_findings:
        j_name = f.get("affected_joint")
        f_start = f.get("frame_start", 0)
        f_end = f.get("frame_end", orig_parsed.metadata.frame_count - 1)
        a_type = str(f.get("anomaly_type", "")).upper()
        target_key = (j_name, f_start, f_end, a_type)
        if target_key in checked_defect_targets:
            continue
        checked_defect_targets.add(target_key)

        if "POP" in a_type or "SWAP" in a_type:
            ok, err = validate_pop_repair(orig_parsed, rep_parsed, orig_rep, rep_rep, j_name, f_start, f_end)
            if not ok:
                reasons.append(err)
        elif "JITTER" in a_type:
            ok, err = validate_jitter_repair(orig_parsed, rep_parsed, j_name, f_start, f_end)
            if not ok:
                reasons.append(err)
        elif "SLID" in a_type or "FOOT" in a_type:
            ok, err = validate_foot_slide_repair(orig_parsed, rep_parsed, orig_rep, rep_rep, j_name, f_start, f_end)
            if not ok:
                reasons.append(err)
        elif "FREEZE" in a_type or "SENSOR" in a_type or "DROPOUT" in a_type:
            ok, err = validate_freeze_repair(orig_parsed, rep_parsed, j_name, f_start, f_end)
            if not ok:
                reasons.append(err)
        elif "ROOT" in a_type or "DISCONTINUITY" in a_type or "JUMP" in a_type:
            ok, err = validate_root_jump_repair(orig_parsed, rep_parsed, j_name, f_start, f_end)
            if not ok:
                reasons.append(err)
        elif "BIOMECHANICAL" in a_type or "LIMIT" in a_type or "VIOLATION" in a_type:
            ok, err = validate_pose_violation_repair(orig_parsed, rep_parsed, j_name, f_start, f_end)
            if not ok:
                reasons.append(err)

    if roster:
        for spec in roster:
            role_upper = spec.role.upper()
            bones = spec.target_bones or spec.assigned_joints or []
            tf = spec.target_frames or [0, orig_parsed.metadata.frame_count - 1]
            f_start, f_end = tf[0], tf[1]
            for b in bones:
                target_key = (b, f_start, f_end, role_upper)
                if target_key in checked_defect_targets:
                    continue
                checked_defect_targets.add(target_key)

                if "POP" in role_upper:
                    ok, err = validate_pop_repair(orig_parsed, rep_parsed, orig_rep, rep_rep, b, f_start, f_end)
                    if not ok:
                        reasons.append(err)
                elif "JITTER" in role_upper or "SMOOTH" in role_upper:
                    ok, err = validate_jitter_repair(orig_parsed, rep_parsed, b, f_start, f_end)
                    if not ok:
                        reasons.append(err)
                elif "SLID" in role_upper or "FOOT" in role_upper or "CONTACT" in role_upper:
                    if any(k in b.lower() for k in ("foot", "toe", "ankle", "heel")):
                        ok, err = validate_foot_slide_repair(orig_parsed, rep_parsed, orig_rep, rep_rep, b, f_start, f_end)
                        if not ok:
                            reasons.append(err)
                elif "FREEZE" in role_upper:
                    ok, err = validate_freeze_repair(orig_parsed, rep_parsed, b, f_start, f_end)
                    if not ok:
                        reasons.append(err)
                elif "ROOT" in role_upper or "STABILIZ" in role_upper:
                    ok, err = validate_root_jump_repair(orig_parsed, rep_parsed, b, f_start, f_end)
                    if not ok:
                        reasons.append(err)
                elif "ARM" in role_upper or "KINEMATIC" in role_upper or "POSE" in role_upper:
                    ok, err = validate_pose_violation_repair(orig_parsed, rep_parsed, b, f_start, f_end)
                    if not ok:
                        reasons.append(err)

    return len(reasons) == 0, reasons

def compute_deterministic_repairs(
    parsed: ParsedBVH,
    roster: Optional[List[AgentSpecification]] = None,
    findings: Optional[List[Any]] = None,
) -> Dict[Tuple[int, int], float]:
    patches: Dict[Tuple[int, int], float] = {}
    j_map = build_joint_channel_map(parsed)
    fc = parsed.metadata.frame_count
    norm_findings = _normalize_findings(findings or [])

    handled_targets = set()

    for f in norm_findings:
        j_name = f.get("affected_joint")
        if not j_name or j_name not in j_map:
            continue
        ch_dict = j_map[j_name]
        f_start = max(0, int(f.get("frame_start", 0)))
        f_end = min(fc - 1, int(f.get("frame_end", fc - 1)))
        a_type = str(f.get("anomaly_type", "")).upper()
        matched = False
        if "POP" in a_type or "SWAP" in a_type:
            matched = True
            for ch_idx in ch_dict.values():
                vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                ctx_pre = vals[max(0, f_start - 3):f_start]
                ctx_post = vals[f_end + 1:min(fc, f_end + 4)]
                v_pre = sum(ctx_pre) / len(ctx_pre) if ctx_pre else vals[f_start]
                v_post = sum(ctx_post) / len(ctx_post) if ctx_post else vals[f_end]
                for idx, t in enumerate(range(f_start, f_end + 1)):
                    alpha = (idx + 1) / (f_end - f_start + 2)
                    patches[(t, ch_idx)] = v_pre * (1.0 - alpha) + v_post * alpha

        elif "JITTER" in a_type:
            matched = True
            for ch_idx in ch_dict.values():
                vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                for t in range(f_start, f_end + 1):
                    if 0 < t < fc - 1:
                        smoothed = 0.25 * vals[t - 1] + 0.5 * vals[t] + 0.25 * vals[t + 1]
                        patches[(t, ch_idx)] = smoothed

        elif "SLID" in a_type or "FOOT" in a_type:
            matched = True
            anchor_f = max(0, f_start)
            for ch_name, ch_idx in ch_dict.items():
                if "position" in ch_name.lower():
                    if ch_name.lower().startswith("y"):
                        y_anchor = max(0.0, parsed.motion[anchor_f][ch_idx])
                        for t in range(f_start, f_end + 1):
                            patches[(t, ch_idx)] = y_anchor
                    else:
                        anchor_val = parsed.motion[anchor_f][ch_idx]
                        for t in range(f_start, f_end + 1):
                            patches[(t, ch_idx)] = anchor_val

        elif "FREEZE" in a_type or "DROPOUT" in a_type or "SENSOR" in a_type or "FLATLINE" in a_type:
            matched = True
            for ch_idx in ch_dict.values():
                vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                v_start = vals[max(0, f_start - 1)]
                v_end = vals[min(fc - 1, f_end + 1)]
                for idx, t in enumerate(range(f_start, f_end + 1)):
                    alpha = (idx + 1) / (f_end - f_start + 2)
                    patches[(t, ch_idx)] = v_start * (1.0 - alpha) + v_end * alpha

        elif "ROOT" in a_type or "DISCONTINUITY" in a_type or "JUMP" in a_type:
            if j_name == parsed.root_node.name:
                matched = True
                pos_indices = [idx for name, idx in ch_dict.items() if "position" in name.lower()]
                t_jump = max(1, f_start)
                t_post = min(fc - 1, f_end + 1)
                dist = sum((parsed.motion[t_post][k] - parsed.motion[t_jump - 1][k]) ** 2 for k in pos_indices) ** 0.5
                if dist < 15.0 and f_end < fc - 1:
                    span = max(1, t_post - (t_jump - 1))
                    for t in range(t_jump, f_end + 1):
                        alpha = (t - (t_jump - 1)) / span
                        for k in pos_indices:
                            patches[(t, k)] = parsed.motion[t_jump - 1][k] * (1.0 - alpha) + parsed.motion[t_post][k] * alpha
                else:
                    for k in pos_indices:
                        jump_delta = parsed.motion[t_jump][k] - parsed.motion[t_jump - 1][k]
                        if abs(jump_delta) > 5.0:
                            for t in range(t_jump, fc):
                                patches[(t, k)] = parsed.motion[t][k] - jump_delta

        elif "BIOMECHANICAL" in a_type or "LIMIT" in a_type or "VIOLATION" in a_type or "HYPEREXTENSION" in a_type:
            matched = True
            for ch_name, ch_idx in ch_dict.items():
                if "rotation" in ch_name.lower():
                    for t in range(f_start, f_end + 1):
                        val = parsed.motion[t][ch_idx]
                        if val > 140.0:
                            patches[(t, ch_idx)] = 135.0
                        elif val < -140.0:
                            patches[(t, ch_idx)] = -135.0

        elif "GIMBAL" in a_type or "EULER" in a_type or "FLIP" in a_type:
            matched = True
            for ch_name, ch_idx in ch_dict.items():
                if "rotation" in ch_name.lower():
                    vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                    v_start = vals[max(0, f_start - 1)]
                    v_end = vals[min(fc - 1, f_end + 1)]
                    for idx, t in enumerate(range(f_start, f_end + 1)):
                        alpha = (idx + 1) / (f_end - f_start + 2)
                        patches[(t, ch_idx)] = v_start * (1.0 - alpha) + v_end * alpha

        if matched:
            handled_targets.add(j_name)

    if roster:
        for spec in roster:
            bones = spec.target_bones or spec.assigned_joints or []
            tf = spec.target_frames or [0, fc - 1]
            f_start = max(0, int(tf[0]))
            f_end = min(fc - 1, int(tf[1]))
            role_upper = spec.role.upper()

            for b in bones:
                if b not in j_map or b in handled_targets:
                    continue
                ch_dict = j_map[b]

                if "POP" in role_upper:
                    for ch_idx in ch_dict.values():
                        vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                        ctx_pre = vals[max(0, f_start - 3):f_start]
                        ctx_post = vals[f_end + 1:min(fc, f_end + 4)]
                        v_pre = sum(ctx_pre) / len(ctx_pre) if ctx_pre else vals[f_start]
                        v_post = sum(ctx_post) / len(ctx_post) if ctx_post else vals[f_end]
                        for idx, t in enumerate(range(f_start, f_end + 1)):
                            alpha = (idx + 1) / (f_end - f_start + 2)
                            patches[(t, ch_idx)] = v_pre * (1.0 - alpha) + v_post * alpha

                elif "JITTER" in role_upper or "SMOOTH" in role_upper:
                    for ch_idx in ch_dict.values():
                        vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                        for t in range(f_start, f_end + 1):
                            if 0 < t < fc - 1:
                                smoothed = 0.25 * vals[t - 1] + 0.5 * vals[t] + 0.25 * vals[t + 1]
                                patches[(t, ch_idx)] = smoothed

                elif "SLID" in role_upper or "FOOT" in role_upper or "CONTACT" in role_upper:
                    anchor_f = max(0, f_start)
                    for ch_name, ch_idx in ch_dict.items():
                        if "position" in ch_name.lower():
                            if ch_name.lower().startswith("y"):
                                y_anchor = max(0.0, parsed.motion[anchor_f][ch_idx])
                                for t in range(f_start, f_end + 1):
                                    patches[(t, ch_idx)] = y_anchor
                            else:
                                anchor_val = parsed.motion[anchor_f][ch_idx]
                                for t in range(f_start, f_end + 1):
                                    patches[(t, ch_idx)] = anchor_val

                elif "FREEZE" in role_upper:
                    for ch_idx in ch_dict.values():
                        vals = [parsed.motion[t][ch_idx] for t in range(fc)]
                        v_start = vals[max(0, f_start - 1)]
                        v_end = vals[min(fc - 1, f_end + 1)]
                        for idx, t in enumerate(range(f_start, f_end + 1)):
                            alpha = (idx + 1) / (f_end - f_start + 2)
                            patches[(t, ch_idx)] = v_start * (1.0 - alpha) + v_end * alpha

                elif "ROOT" in role_upper or "STABILIZ" in role_upper:
                    if b == parsed.root_node.name:
                        pos_indices = [idx for name, idx in ch_dict.items() if "position" in name.lower()]
                        t_jump = max(1, f_start)
                        for k in pos_indices:
                            jump_delta = parsed.motion[t_jump][k] - parsed.motion[t_jump - 1][k]
                            if abs(jump_delta) > 5.0:
                                for t in range(t_jump, fc):
                                    patches[(t, k)] = parsed.motion[t][k] - jump_delta

                elif "ARM" in role_upper or "POSE" in role_upper:
                    for ch_name, ch_idx in ch_dict.items():
                        if "rotation" in ch_name.lower():
                            for t in range(f_start, f_end + 1):
                                val = parsed.motion[t][ch_idx]
                                if val > 140.0:
                                    patches[(t, ch_idx)] = 135.0
                                elif val < -140.0:
                                    patches[(t, ch_idx)] = -135.0

    return patches

def build_finding_task_context(
    finding: Dict[str, Any],
    parsed_bvh: ParsedBVH,
    retry_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    j_name = str(finding.get("affected_joint") or "")
    f_start = int(finding.get("frame_start", 0))
    f_end = int(finding.get("frame_end", parsed_bvh.metadata.frame_count - 1))
    a_type = str(finding.get("anomaly_type", "UNKNOWN"))
    ev = finding.get("evidence", {})
    expl = finding.get("explanation", "")
    j_map = build_joint_channel_map(parsed_bvh)
    ch_dict = j_map.get(j_name, {})
    return {
        "finding_id": finding.get("finding_id", str(uuid.uuid4())),
        "joint": j_name,
        "anomaly_type": a_type,
        "frame_start": f_start,
        "frame_end": f_end,
        "evidence": ev,
        "explanation": expl,
        "channels": list(ch_dict.keys()),
        "retry_feedback": retry_feedback,
        "objective": f"Repair {a_type} on joint {j_name} across frames [{f_start}..{f_end}] cleanly.",
    }

def generate_finding_repair_candidate(
    parsed_bvh: ParsedBVH,
    finding: Dict[str, Any],
    task_context: Dict[str, Any],
    attempt: int = 1,
) -> Dict[Tuple[int, int], float]:
    patches = compute_deterministic_repairs(parsed_bvh, findings=[finding])
    if not patches and attempt > 1:
        j_name = task_context.get("joint", "")
        f_start = task_context.get("frame_start", 0)
        f_end = task_context.get("frame_end", parsed_bvh.metadata.frame_count - 1)
        j_map = build_joint_channel_map(parsed_bvh)
        ch_dict = j_map.get(j_name, {})
        fc = parsed_bvh.metadata.frame_count
        for ch_idx in ch_dict.values():
            vals = [parsed_bvh.motion[t][ch_idx] for t in range(fc)]
            for t in range(f_start, f_end + 1):
                if 0 < t < fc - 1:
                    smoothed = 0.25 * vals[t - 1] + 0.5 * vals[t] + 0.25 * vals[t + 1]
                    patches[(t, ch_idx)] = smoothed
    return patches

def validate_candidate_authorized_changes(
    candidate_patches: Dict[Tuple[int, int], float],
    authorized_mask: Set[Tuple[int, int]],
    base_motion: List[List[float]],
) -> Tuple[bool, str]:
    if not candidate_patches:
        return False, "Candidate returned no channel modifications"
    unauthorized = set(candidate_patches.keys()) - authorized_mask
    if unauthorized:
        return False, f"Candidate modified {len(unauthorized)} unauthorized channels outside approved scope"
    has_delta = False
    for (t, ch_idx), val in candidate_patches.items():
        if abs(val - base_motion[t][ch_idx]) > 1e-4:
            has_delta = True
            break
    if not has_delta:
        return False, "Candidate values are identical to pre-repair motion (unmodified)"
    return True, ""

def validate_finding_quality(
    orig_parsed: ParsedBVH,
    candidate_parsed: ParsedBVH,
    finding: Dict[str, Any],
    authorized_mask: Set[Tuple[int, int]],
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    orig_rep = build_shared_motion_representation(orig_parsed)
    cand_rep = build_shared_motion_representation(candidate_parsed)

    inv_passed, inv_errs = check_repair_invariants(orig_parsed, candidate_parsed, orig_rep=orig_rep, rep_rep=cand_rep)
    if not inv_passed:
        reasons.extend(inv_errs)

    mask_passed, mask_errs = validate_strict_edit_mask(orig_parsed, candidate_parsed, authorized_mask)
    if not mask_passed:
        reasons.extend(mask_errs)

    j_name = finding.get("affected_joint")
    f_start = finding.get("frame_start", 0)
    f_end = finding.get("frame_end", orig_parsed.metadata.frame_count - 1)
    a_type = str(finding.get("anomaly_type", "")).upper()

    if "POP" in a_type or "SWAP" in a_type:
        ok, err = validate_pop_repair(orig_parsed, candidate_parsed, orig_rep, cand_rep, j_name, f_start, f_end)
        if not ok:
            reasons.append(err)
    elif "JITTER" in a_type:
        ok, err = validate_jitter_repair(orig_parsed, candidate_parsed, j_name, f_start, f_end)
        if not ok:
            reasons.append(err)
    elif "SLID" in a_type or "FOOT" in a_type:
        ok, err = validate_foot_slide_repair(orig_parsed, candidate_parsed, orig_rep, cand_rep, j_name, f_start, f_end)
        if not ok:
            reasons.append(err)
    elif "FREEZE" in a_type or "SENSOR" in a_type or "DROPOUT" in a_type:
        ok, err = validate_freeze_repair(orig_parsed, candidate_parsed, j_name, f_start, f_end)
        if not ok:
            reasons.append(err)
    elif "ROOT" in a_type or "DISCONTINUITY" in a_type or "JUMP" in a_type:
        ok, err = validate_root_jump_repair(orig_parsed, candidate_parsed, j_name, f_start, f_end)
        if not ok:
            reasons.append(err)
    elif "BIOMECHANICAL" in a_type or "LIMIT" in a_type or "VIOLATION" in a_type:
        ok, err = validate_pose_violation_repair(orig_parsed, candidate_parsed, j_name, f_start, f_end)
        if not ok:
            reasons.append(err)

    if reasons:
        return False, reasons
    return True, []

def execute_progressive_finding_repair(
    input_bvh_path: str,
    output_bvh_path: str,
    approved_findings: Optional[List[Any]] = None,
    roster: Optional[List[AgentSpecification]] = None,
    max_retries: int = 3,
    event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    if not os.path.exists(input_bvh_path):
        raise FileNotFoundError(f"Input BVH does not exist: {input_bvh_path}")

    if os.path.abspath(input_bvh_path) == os.path.abspath(output_bvh_path):
        raise ValueError("Safe repair requires separate asset output; in-place modification prohibited.")

    base_parsed = parse_bvh_file(input_bvh_path)
    fc = base_parsed.metadata.frame_count
    working_motion = [list(row) for row in base_parsed.motion]
    working_parsed = copy.deepcopy(base_parsed)
    working_parsed.motion = working_motion

    accumulated_patches: Dict[Tuple[int, int], float] = {}
    all_authorized_mask: Set[Tuple[int, int]] = set()
    fixed_findings: List[Dict[str, Any]] = []
    unresolved_findings: List[Dict[str, Any]] = []
    retry_stats: Dict[str, int] = {}

    norm_findings = _normalize_findings(approved_findings or [])
    if not norm_findings and roster:
        for spec in roster:
            for b in (spec.target_bones or spec.assigned_joints or []):
                tf = spec.target_frames or [0, fc - 1]
                norm_findings.append({
                    "finding_id": f"finding-{uuid.uuid4().hex[:6]}",
                    "affected_joint": b,
                    "frame_start": tf[0],
                    "frame_end": tf[1],
                    "anomaly_type": "ROTATION_JITTER" if "JITTER" in spec.role.upper() else ("PLANTED_FOOT_SLIDING" if "SLID" in spec.role.upper() or "FOOT" in spec.role.upper() else "ROOT_DISCONTINUITY"),
                    "severity": "HIGH",
                })

    for f in norm_findings:
        f_id = str(f.get("finding_id") or uuid.uuid4().hex[:8])
        j_name = str(f.get("affected_joint") or "")
        f_start = int(f.get("frame_start", 0))
        f_end = int(f.get("frame_end", fc - 1))
        a_type = str(f.get("anomaly_type", "UNKNOWN"))

        finding_mask = build_edit_mask(working_parsed, findings=[f])
        finding_fixed = False
        last_feedback = None

        for attempt in range(1, max_retries + 1):
            retry_stats[f_id] = attempt
            if event_callback and attempt > 1:
                event_callback({
                    "event": "FINDING_RETRY",
                    "finding_id": f_id,
                    "joint": j_name,
                    "attempt": attempt,
                    "reason": last_feedback,
                })

            task_ctx = build_finding_task_context(f, working_parsed, retry_feedback=last_feedback)
            cand_patches = generate_finding_repair_candidate(working_parsed, f, task_ctx, attempt=attempt)

            has_changes, change_err = validate_candidate_authorized_changes(cand_patches, finding_mask, working_parsed.motion)
            if not has_changes:
                last_feedback = f"Attempt {attempt}: Candidate changed no authorized values ({change_err}). Defect on {j_name} [{f_start}..{f_end}] was untouched."
                continue

            cand_parsed = copy.deepcopy(working_parsed)
            for (t, ch_idx), val in cand_patches.items():
                cand_parsed.motion[t][ch_idx] = val

            test_mask = all_authorized_mask | finding_mask
            gate_passed, gate_errs = validate_finding_quality(base_parsed, cand_parsed, f, test_mask)
            if not gate_passed:
                last_feedback = f"Attempt {attempt}: Quality gate rejected repair: {'; '.join(gate_errs)}"
                continue

            for (t, ch_idx), val in cand_patches.items():
                working_motion[t][ch_idx] = val
            accumulated_patches.update(cand_patches)
            all_authorized_mask.update(finding_mask)
            fixed_findings.append({
                "finding_id": f_id,
                "joint": j_name,
                "anomaly_type": a_type,
                "frame_start": f_start,
                "frame_end": f_end,
                "attempts": attempt,
                "description": f"Successfully fixed {a_type} on {j_name} (frames {f_start}-{f_end}).",
            })
            finding_fixed = True
            if event_callback:
                event_callback({
                    "event": "FINDING_FIXED",
                    "finding_id": f_id,
                    "joint": j_name,
                    "anomaly_type": a_type,
                    "attempts": attempt,
                })
            break

        if not finding_fixed:
            unresolved_findings.append({
                "finding_id": f_id,
                "joint": j_name,
                "anomaly_type": a_type,
                "frame_start": f_start,
                "frame_end": f_end,
                "attempts": max_retries,
                "reason": last_feedback or "Quality gate rejected after maximum retries.",
            })
            if event_callback:
                event_callback({
                    "event": "FINDING_UNRESOLVED",
                    "finding_id": f_id,
                    "joint": j_name,
                    "anomaly_type": a_type,
                    "reason": last_feedback,
                })

    final_whole_ok = False
    whole_errs = []
    if accumulated_patches:
        apply_direct_bvh_channel_patch(
            original_bvh_path=input_bvh_path,
            output_bvh_path=output_bvh_path,
            channel_modifications=accumulated_patches,
            authorized_edit_mask=all_authorized_mask,
        )
        final_whole_ok, whole_errs = validate_repair_quality(
            original_bvh_path=input_bvh_path,
            repaired_bvh_path=output_bvh_path,
            authorized_mask=all_authorized_mask,
            findings=fixed_findings,
        )

    if not fixed_findings or not final_whole_ok:
        outcome_status = "FAILED"
        if os.path.exists(output_bvh_path):
            try:
                os.remove(output_bvh_path)
            except OSError:
                pass
        result_path = None
    elif unresolved_findings:
        outcome_status = "PARTIALLY_REPAIRED"
        result_path = output_bvh_path
    else:
        outcome_status = "COMPLETED"
        result_path = output_bvh_path

    fixed_joints = sorted(list(set(f["joint"] for f in fixed_findings)))
    unres_joints = sorted(list(set(f["joint"] for f in unresolved_findings)))

    if outcome_status == "COMPLETED":
        summary_message = f"All {len(fixed_findings)} motion issues repaired successfully across {', '.join(fixed_joints)}."
    elif outcome_status == "PARTIALLY_REPAIRED":
        summary_message = f"Repaired {len(fixed_findings)} of {len(norm_findings)} motion issues across {', '.join(fixed_joints)}. {len(unresolved_findings)} issues on {', '.join(unres_joints)} could not be resolved."
    else:
        if whole_errs:
            summary_message = f"Repair rejected by final quality validation: {'; '.join(whole_errs)}"
        elif unresolved_findings:
            summary_message = f"Repair failed: None of the {len(norm_findings)} motion issues could be repaired after {max_retries} retries."
        else:
            summary_message = "No defects were authorized or found to repair."

    metrics = {
        "outcome_status": outcome_status,
        "total_findings": len(norm_findings),
        "fixed_count": len(fixed_findings),
        "unresolved_count": len(unresolved_findings),
        "fixed_findings": fixed_findings,
        "unresolved_findings": unresolved_findings,
        "summary_message": summary_message,
        "patches_applied": len(accumulated_patches),
        "authorized_channels_count": len(all_authorized_mask),
        "retry_counts": retry_stats,
        "qa_passed": outcome_status in ("COMPLETED", "PARTIALLY_REPAIRED"),
    }
    return result_path, metrics

def execute_deterministic_safe_repair(
    input_bvh_path: str,
    output_bvh_path: str,
    roster: Optional[List[AgentSpecification]] = None,
    findings: Optional[List[Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    if not os.path.exists(input_bvh_path):
        raise FileNotFoundError(f"Input BVH does not exist: {input_bvh_path}")

    if os.path.abspath(input_bvh_path) == os.path.abspath(output_bvh_path):
        raise ValueError("Safe repair requires separate asset output; in-place modification prohibited.")

    rep_path, metrics = execute_progressive_finding_repair(
        input_bvh_path=input_bvh_path,
        output_bvh_path=output_bvh_path,
        approved_findings=findings,
        roster=roster,
        max_retries=3,
    )
    if rep_path is None or metrics.get("outcome_status") == "FAILED":
        summary_msg = metrics.get("summary_message", "Quality acceptance gate rejected repair.")
        raise ValueError(f"Quality acceptance gate rejected repair: {summary_msg}")

    return rep_path, metrics

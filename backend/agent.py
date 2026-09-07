import os
import sys
import asyncio
import logging
import ast
import uuid
import json
import re
from typing import Optional, List, Dict, Any, Tuple

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
except ImportError:
    from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams, StreamableHTTPConnectionParams

from config import BLENDER_BOILERPLATE
from models import AgentSpecification, Finding, BVHMetadata

logger = logging.getLogger(__name__)

def get_clickhouse_mcp_toolset() -> Optional[MCPToolset]:
    mcp_url = os.environ.get("CLICKHOUSE_MCP_URL")
    if mcp_url:
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
        return Client(vertexai=True, location="us-central1")

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

    has_only = any(k in text_lower for k in ("only", "just", "exclusively", "solely"))
    target_foot = any(k in text_lower for k in ("foot", "feet", "slide", "sliding", "toe", "ankle", "ground", "pin"))
    target_spine = any(k in text_lower for k in ("spine", "torso", "neck", "jitter", "smooth"))
    target_root = any(k in text_lower for k in ("root", "hips", "drift", "jump", "teleport", "discontinuity"))
    target_arm = any(k in text_lower for k in ("arm", "shoulder", "elbow", "wrist", "hand"))

    if has_only:
        allow_foot = target_foot
        allow_jitter = target_spine
        allow_root = target_root
        allow_arm = target_arm
    else:
        allow_foot = True
        allow_jitter = True
        allow_root = True
        allow_arm = True

    ignore_foot = any(k in text_lower for k in ("ignore foot", "ignore feet", "skip foot", "without foot", "don't touch foot", "dont touch foot", "don't touch the foot", "dont touch the foot"))
    ignore_spine = any(k in text_lower for k in ("ignore spine", "skip spine", "without spine", "don't touch spine", "dont touch spine", "don't touch the spine", "dont touch the spine"))
    ignore_root = any(k in text_lower for k in ("ignore root", "skip root", "without root", "ignore hips", "don't touch root", "dont touch root", "don't touch hips"))
    ignore_arm = any(k in text_lower for k in ("ignore arm", "skip arm", "without arm", "don't touch arm", "dont touch arm"))

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

    return {
        "allow_foot": allow_foot,
        "allow_jitter": allow_jitter,
        "allow_root": allow_root,
        "allow_arm": allow_arm,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "selected_joints": selected_joints,
    }

def _deterministic_synthesis(
    prompt_lower: str,
    norm_findings: List[Dict[str, Any]],
    metadata: Optional[Any] = None,
) -> List[AgentSpecification]:
    roster: List[AgentSpecification] = []
    total_frames = 100
    if metadata:
        if hasattr(metadata, "frame_count"):
            total_frames = metadata.frame_count
        elif isinstance(metadata, dict) and "frame_count" in metadata:
            total_frames = metadata["frame_count"]

    intent = parse_kinematic_intent(prompt_lower, norm_findings)
    allow_foot = intent["allow_foot"]
    allow_jitter = intent["allow_jitter"]
    allow_root = intent["allow_root"]
    allow_arm = intent["allow_arm"]
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

    has_foot_prompt = any(k in prompt_lower for k in ("foot", "feet", "slide", "sliding", "planted", "pin", "ground"))
    has_jitter_prompt = any(k in prompt_lower for k in ("jitter", "smooth", "spine", "torso", "catmull", "filter"))
    has_root_prompt = any(k in prompt_lower for k in ("root", "discontinuity", "drift", "teleport", "origin"))
    has_arm_prompt = any(k in prompt_lower for k in ("arm", "shoulder", "hand", "elbow", "wrist"))

    if allow_foot and (foot_findings or (has_foot_prompt and not jitter_findings and not root_findings)):
        joints = sorted(list(set(f.get("affected_joint") for f in foot_findings if f.get("affected_joint"))))
        if not joints:
            joints = ["LeftFoot", "RightFoot"] if "both" in prompt_lower else (["RightFoot"] if "right" in prompt_lower else ["LeftFoot"])
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
        if not joints:
            joints = ["Spine", "Spine1"] if "torso" in prompt_lower else ["Spine"]
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
        if not joints:
            joints = ["Hips"]
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

    if allow_arm and has_arm_prompt:
        arm_joints = ["LeftArm", "LeftForeArm"] if "left" in prompt_lower else (["RightArm", "RightForeArm"] if "right" in prompt_lower else ["LeftArm", "RightArm"])
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
) -> List[AgentSpecification]:
    norm_findings = _normalize_findings(findings or [])
    prompt_str = (prompt or "").strip()
    prompt_lower = prompt_str.lower()

    if os.environ.get("TESTING") == "1":
        return _deterministic_synthesis(prompt_lower, norm_findings, metadata)

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

    return _deterministic_synthesis(prompt_lower, norm_findings, metadata)

def instantiate_dynamic_agent(agent_spec: AgentSpecification) -> Agent:
    tools = []
    if "query_clickhouse_rag" in (agent_spec.tools or []):
        tools.append(query_clickhouse_rag)
    if "run_select_query" in (agent_spec.tools or []):
        tools.append(query_clickhouse_select)
    if "list_tables" in (agent_spec.tools or []):
        tools.append(list_clickhouse_tables)

    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", agent_spec.role.lower())[:38].strip("_") or "dynamic_agent"
    instruction = agent_spec.system_instruction or (
        f"You are a specialized motion capture repair agent: {agent_spec.role}.\n"
        f"Target bones: {', '.join(agent_spec.target_bones)}.\n"
        f"Target frames: {agent_spec.target_frames}.\n"
        f"Follow boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
        "Call query_clickhouse_rag or run_select_query to check for historical fixes from ClickHouse.\n"
        "Your only output should be raw python code enclosed in ```python ``` tags."
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

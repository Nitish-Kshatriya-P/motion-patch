import os
import sys
import asyncio
import logging
import ast
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from config import BLENDER_BOILERPLATE

from google.adk.models import Gemini
from google.genai import Client
from functools import cached_property

class VertexGemini(Gemini):
    @cached_property
    def api_client(self) -> Client:
        return Client(vertexai=True, location="us-central1")

logger = logging.getLogger(__name__)

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
    if _mcp_session_ctx:
        await _mcp_session_ctx.__aexit__(None, None, None)
    if _mcp_client_ctx:
        await _mcp_client_ctx.__aexit__(None, None, None)

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

def validate_script_ast(script_code: str) -> str:
    try:
        tree = ast.parse(script_code)
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"
        
    has_bpy = False
    writes_to_output = False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "bpy":
                    has_bpy = True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "bpy":
                has_bpy = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "output.bvh" in node.value:
                writes_to_output = True
                
    if not has_bpy:
        return "Validation Error: The script must import 'bpy'."
    if not writes_to_output:
        return "Validation Error: The script does not appear to write to '/workspace/output.bvh'."
        
    return ""

def validate_physical_constraints(script_code: str, expert_type: ExpertType) -> str:
    if expert_type == ExpertType.CONTACT:
        if "ik" not in script_code.lower() and "constraint" not in script_code.lower():
            return "Physical Constraint Error: Contact expert must implement IK or constraints to prevent foot sliding."
    elif expert_type == ExpertType.KINEMATICS:
        if "bpy.ops.graph" in script_code or "bpy.ops.action" in script_code:
            return "Context Error: Do not use bpy.ops.graph.* or bpy.ops.action.* in headless mode."
    return ""

from enum import Enum

class ExpertType(str, Enum):
    KINEMATICS = "KINEMATICS"
    CONTACT = "CONTACT"

async def query_clickhouse_rag(query: str) -> str:
    if not mcp_session:
        return "MCP Session not initialized"
    try:
        mcp_result = await mcp_session.call_tool("query_rag_memory", arguments={"anomaly_query": query})
        text = mcp_result.content[0].text if mcp_result.content else ""
        return text
    except Exception as e:
        return f"Tool call failed: {e}"

async def generate_blender_script(bvh_content: str, instruction_payload) -> str:
    supervisor = Agent(
        name="supervisor",
        instruction=(
            "You are a routing agent for a Mocap Studio. Read the user's prompt (or infer from audio) "
            "and classify the anomaly into one of two categories: 'Kinematics' (e.g. smoothing, jitter, IK) "
            "or 'Contact' (e.g. foot sliding, ground collisions). Reply with ONLY the word KINEMATICS or CONTACT."
        ),
        model=VertexGemini(model="gemini-2.5-flash"),
    )
    
    runner = InMemoryRunner(agent=supervisor)
    sup_contents = [f"User Request: {instruction_payload.prompt}"]
    if instruction_payload and instruction_payload.audio_data:
        sup_contents.append(types.Part.from_bytes(data=instruction_payload.audio_data, mime_type=instruction_payload.audio_mime))
        
    events = await runner.run_debug(sup_contents)
    raw_type = extract_text_from_events(events).strip().upper() if events else "KINEMATICS"
    expert_type = ExpertType.CONTACT if "CONTACT" in raw_type else ExpertType.KINEMATICS
        
    logger.info(f"Supervisor routed to: {expert_type.value}")
    
    if expert_type == ExpertType.CONTACT:
        expert = Agent(
            name="contact_worker",
            instruction=(
                "You are an expert Blender Python developer for motion capture cleanup.\n"
                f"You must strictly follow the boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                "Guidelines: Use inverse kinematics (IK) or constraint baking to firmly pin bones (e.g., feet) above z=0.\n"
                "You MUST call the query_clickhouse_rag tool to check for similar past fixes before generating your code.\n"
                "Your only output should be the raw python code enclosed in ```python ``` tags."
            ),
            model=VertexGemini(model="gemini-2.5-flash"),
            tools=[query_clickhouse_rag]
        )
    else:
        expert = Agent(
            name="kinematics_worker",
            instruction=(
                "You are an expert Blender Python developer for motion capture cleanup.\n"
                f"You must strictly follow the boilerplate pattern:\n{BLENDER_BOILERPLATE.replace('{', '<').replace('}', '>')}\n"
                "CRITICAL: Do NOT use bpy.ops.graph.* or bpy.ops.action.* as they require UI context. Modify fcurve.keyframe_points or NLA strips directly.\n"
                "Your only output should be the raw python code enclosed in ```python ``` tags."
            ),
            model=VertexGemini(model="gemini-2.5-flash"),
            tools=[query_clickhouse_rag]
        )
    
    expert_runner = InMemoryRunner(agent=expert)
    
    text_prompt = f"Original BVH File:\n```bvh\n{bvh_content}\n```"
    if instruction_payload.prompt:
        text_prompt += f"\n\nUser Request: {instruction_payload.prompt}"
        
    req_contents = []
    if instruction_payload and instruction_payload.audio_data:
        text_prompt += f"\n\nUser instructions are provided in the attached audio."
        req_contents.append(text_prompt)
        req_contents.append(types.Part.from_bytes(data=instruction_payload.audio_data, mime_type=instruction_payload.audio_mime))
    else:
        req_contents.append(text_prompt)

    max_attempts = 3
    qa_prompt = (
        "You are a QA Judge Agent for Blender Python scripts. Evaluate the provided script against basic physical constraints "
        "(e.g., no flying away, smooth transitions, correct bone references). "
        "If it passes, reply 'PASS'. If it fails, reply 'FAIL: ' followed by a brief description of the issue."
    )
    qa_agent = Agent(
        name="QA",
        instruction=qa_prompt,
        model=VertexGemini(model="gemini-2.5-flash")
    )
    qa_runner = InMemoryRunner(agent=qa_agent)
    
    for attempt in range(max_attempts):
        logger.info(f"Expert Agent generating code (Attempt {attempt+1}/{max_attempts})...")
        events = await expert_runner.run_debug(req_contents)
        response_text = extract_text_from_events(events) if events else ""
        script_code = extract_code(response_text)
        
        ast_error = validate_script_ast(script_code)
        constraint_error = validate_physical_constraints(script_code, expert_type)
        if ast_error:
            qa_result = f"FAIL: {ast_error}"
        elif constraint_error:
            qa_result = f"FAIL: {constraint_error}"
        else:
            qa_events = await qa_runner.run_debug([f"Evaluate this script:\n```python\n{script_code}\n```"])
            qa_result = extract_text_from_events(qa_events).strip() if qa_events else "FAIL"
            
        if qa_result.startswith("PASS"):
            logger.info("QA Judge passed the script.")
            return script_code
            
        if attempt == max_attempts - 1:
            logger.error("QA Judge failed all attempts.")
            raise RuntimeError("Agent failed to generate a script that passes QA validation.")
            
        req_contents = [f"QA Judge rejected your script. Fix these issues: {qa_result}"]

    return ""

import os
import sys
import asyncio
import logging
import ast
from google.adk import Agent, Runner
from google.genai import types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from config import BLENDER_BOILERPLATE

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
        name="Supervisor",
        instruction=(
            "You are a routing agent for a Mocap Studio. Read the user's prompt (or infer from audio) "
            "and classify the anomaly into one of two categories: 'Kinematics' (e.g. smoothing, jitter, IK) "
            "or 'Contact' (e.g. foot sliding, ground collisions). Reply with ONLY the word KINEMATICS or CONTACT."
        ),
        model="gemini-3.7-flash"
    )
    
    runner = Runner(agent=supervisor)
    sup_contents = [f"User Request: {instruction_payload.prompt}"]
    if instruction_payload and instruction_payload.audio_data:
        sup_contents.append(types.Part.from_bytes(data=instruction_payload.audio_data, mime_type=instruction_payload.audio_mime))
        
    events = await runner.run_debug(sup_contents)
    raw_type = events[-1].output.text.strip().upper() if events else "KINEMATICS"
    expert_type = ExpertType.CONTACT if "CONTACT" in raw_type else ExpertType.KINEMATICS
        
    logger.info(f"Supervisor routed to: {expert_type.value}")
    
    expert_guidelines = (
        "- For Contact logic: Use inverse kinematics (IK) or constraint baking to firmly pin bones (e.g., feet) above z=0."
    ) if expert_type == ExpertType.CONTACT else (
        "- For Kinematics logic: Use fcurve smoothing, Euler filtering, or low-pass filters to remove jitter."
    )
    
    expert_instruction = (
        "You are an expert Blender Python developer for motion capture cleanup.\n"
        f"You must strictly follow the boilerplate pattern:\n{BLENDER_BOILERPLATE}\n"
        f"Guidelines:\n{expert_guidelines}\n"
        "You MUST call the query_clickhouse_rag tool to check for similar past fixes before generating your code.\n"
        "Your only output should be the raw python code enclosed in ```python ``` tags."
    )
    
    expert = Agent(
        name="Worker",
        instruction=expert_instruction,
        model="gemini-1.5-pro",
        tools=[query_clickhouse_rag]
    )
    
    expert_runner = Runner(agent=expert)
    
    text_prompt = f"Original BVH File:\n```bvh\n{bvh_content}\n```"
    if prompt:
        text_prompt += f"\n\nUser Request: {prompt}"
        
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
        model="gemini-3.7-flash"
    )
    qa_runner = Runner(agent=qa_agent)
    
    for attempt in range(max_attempts):
        logger.info(f"Expert Agent generating code (Attempt {attempt+1}/{max_attempts})...")
        events = await expert_runner.run_debug(req_contents)
        response_text = events[-1].output.text if events else ""
        script_code = extract_code(response_text)
        
        ast_error = validate_script_ast(script_code)
        if ast_error:
            qa_result = f"FAIL: {ast_error}"
        else:
            qa_events = await qa_runner.run_debug([f"Evaluate this script:\n```python\n{script_code}\n```"])
            qa_result = qa_events[-1].output.text.strip() if qa_events else "FAIL"
            
        if qa_result.startswith("PASS"):
            logger.info("QA Judge passed the script.")
            return script_code
            
        if attempt == max_attempts - 1:
            logger.error("QA Judge failed all attempts.")
            raise RuntimeError("Agent failed to generate a script that passes QA validation.")
            
        req_contents = [f"QA Judge rejected your script. Fix these issues: {qa_result}"]

    return ""

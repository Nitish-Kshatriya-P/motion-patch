import os
import sys
import asyncio
import logging
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from config import init_vertexai, BLENDER_BOILERPLATE

logger = logging.getLogger(__name__)

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

def get_function_call(response):
    try:
        content = response.candidates[0].content
        for part in content.parts:
            if hasattr(part, "function_call") and part.function_call:
                return part.function_call, content
    except (IndexError, AttributeError):
        pass
    return None

def get_mcp_text(mcp_result) -> str:
    if getattr(mcp_result, "content", None) and len(mcp_result.content) > 0:
        return getattr(mcp_result.content[0], "text", "")
    return ""

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

from typing import NamedTuple

class AudioPayload(NamedTuple):
    data: bytes
    mime_type: str

async def _run_tool_loop(chat, response, mcp_session):
    while True:
        function_call_info = get_function_call(response)
        if not function_call_info:
            break
        
        function_call, _ = function_call_info
        args_dict = {k: v for k, v in function_call.args.items()} if hasattr(function_call.args, "items") else function_call.args
        try:
            mcp_result = await mcp_session.call_tool(function_call.name, arguments=args_dict)
            result_text = get_mcp_text(mcp_result)
        except Exception as e:
            result_text = f"Tool call failed: {e}"
        
        response = await chat.send_message_async(
            Part.from_function_response(
                name=function_call.name,
                response={"content": result_text}
            ),
            generation_config={"temperature": 0.2}
        )
    return response

async def generate_blender_script(prompt: str, hierarchy_only: str, audio: AudioPayload = None) -> str:
    boilerplate_guidelines = BLENDER_BOILERPLATE.format(fix_logic="- Perform the user's requested modifications using the Blender API on the armature and its bones.").split('\n')
    boilerplate_guidelines_str = "\n".join([f"- {line}" for line in boilerplate_guidelines])
    
    contents = []
    text_prompt = f"Original BVH Skeleton:\n```bvh\n{hierarchy_only}\n```"
    if prompt:
        text_prompt += f"\n\nUser Request: {prompt}"
    if audio:
        text_prompt += f"\n\nUser instructions are provided in the attached audio."
    contents.append(text_prompt)
    
    if audio:
        contents.append(Part.from_data(data=audio.data, mime_type=audio.mime_type))

    init_vertexai()
    
    # 1. Supervisor Agent
    supervisor_prompt = (
        "You are a routing agent. Determine if the user's request is related to 'Kinematics' (e.g. jitter, smoothing, animation adjustment) "
        "or 'Contact' (e.g. foot sliding, ground collisions). Reply with ONLY the word KINEMATICS or CONTACT."
    )
    supervisor = GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=supervisor_prompt
    )
    logger.info("Calling Supervisor Agent...")
    supervisor_resp = await supervisor.generate_content_async(contents, generation_config={"temperature": 0.0})
    expert_type = supervisor_resp.text.strip().upper()
    if expert_type not in ["KINEMATICS", "CONTACT"]:
        expert_type = "KINEMATICS"
    logger.info(f"Supervisor routed to: {expert_type} Expert")
    
    # 2. Expert Agent
    expert_instruction = (
        f"You are a {expert_type.capitalize()} Expert in Blender Python (bpy). Write a python script that will be executed "
        "in headless blender to modify a .bvh file. "
        "Input file: /workspace/input.bvh\n"
        "Output file: /workspace/output.bvh\n"
        "Important guidelines:\n"
        f"{boilerplate_guidelines_str}\n"
        "- Do NOT wrap code in markdown tags like ```python ... ```, just output the raw python code.\n"
        "- Zero comments. Do NOT include any code comments in the generated python script.\n"
        "- You have access to a tool to search past fixes in the RAG memory bank. You MUST use this tool to query ClickHouse for similar past fixes before generating your code."
    )
    
    mcp_tools = await mcp_session.list_tools()
            
    tool_item = mcp_tools.tools[0]
    rag_tool = Tool(function_declarations=[FunctionDeclaration(
        name=tool_item.name,
        description=tool_item.description,
        parameters=tool_item.inputSchema
    )])
    
    expert_model = GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=expert_instruction,
        tools=[rag_tool]
    )
    
    chat = expert_model.start_chat()
    
    logger.info(f"Using {expert_type.capitalize()} Expert for generation.")
    response = await chat.send_message_async(
        contents,
        generation_config={"temperature": 0.2}
    )
    
    response = await _run_tool_loop(chat, response, mcp_session)
    
    # 3. QA Judge Agent
    qa_prompt = (
        "You are a QA Judge Agent for Blender Python scripts. Evaluate the provided script against basic physical constraints "
        "(e.g., no flying away, smooth transitions, correct bone references). "
        "If it passes, reply 'PASS'. If it fails, reply 'FAIL: ' followed by a brief description of the issue."
    )
    qa_model = GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=qa_prompt
    )
    
    max_attempts = 2
    for attempt in range(max_attempts):
        script_code = extract_code(response.text)
        
        qa_contents = [f"Evaluate this script:\n```python\n{script_code}\n```"]
        qa_resp = await qa_model.generate_content_async(qa_contents, generation_config={"temperature": 0.0})
        qa_result = qa_resp.text.strip()
        
        if qa_result.startswith("PASS") or attempt == max_attempts - 1:
            logger.info("QA Judge passed the script.")
            return script_code
        else:
            logger.info(f"QA Failed: {qa_result}. Retrying...")
            response = await chat.send_message_async(
                [f"Your script failed QA. Fix the following issue and generate the full script again:\n{qa_result}"],
                generation_config={"temperature": 0.2}
            )
            response = await _run_tool_loop(chat, response, mcp_session)
            
    return extract_code(response.text)

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

async def generate_blender_script(prompt: str, hierarchy_only: str, audio_data: tuple[bytes, str] = None) -> str:
    boilerplate_guidelines = BLENDER_BOILERPLATE.format(fix_logic="- Perform the user's requested modifications using the Blender API on the armature and its bones.").split('\n')
    boilerplate_guidelines_str = "\n".join([f"- {line}" for line in boilerplate_guidelines])
    
    system_instruction = (
        "You are an expert in Blender Python (bpy). Write a python script that will be executed "
        "in headless blender to modify a .bvh file. "
        "Input file: /workspace/input.bvh\n"
        "Output file: /workspace/output.bvh\n"
        "Important guidelines:\n"
        f"{boilerplate_guidelines_str}\n"
        "- Do NOT wrap code in markdown tags like ```python ... ```, just output the raw python code.\n"
        "- Zero comments. Do NOT include any code comments in the generated python script.\n"
        "- You have access to a tool to search past fixes in the RAG memory bank. You MUST use this tool to query ClickHouse for similar past fixes before generating your code."
    )
    
    contents = []
    text_prompt = f"Original BVH Skeleton:\n```bvh\n{hierarchy_only}\n```"
    if prompt:
        text_prompt += f"\n\nUser Request: {prompt}"
    contents.append(text_prompt)
    
    if audio_data:
        contents.append(Part.from_data(data=audio_data[0], mime_type=audio_data[1]))

    init_vertexai()
    
    mcp_tools = await mcp_session.list_tools()
            
    tool_item = mcp_tools.tools[0]
    rag_tool = Tool(function_declarations=[FunctionDeclaration(
        name=tool_item.name,
        description=tool_item.description,
        parameters=tool_item.inputSchema
    )])
    
    model = GenerativeModel(
        model_name="gemini-2.5-pro",
        system_instruction=system_instruction,
        tools=[rag_tool]
    )
    
    chat = model.start_chat()
    
    logger.info("Using google-cloud-aiplatform (ADK) for generation.")
    response = await chat.send_message_async(
        contents,
        generation_config={"temperature": 0.2}
    )
    
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
        
    return extract_code(response.text)

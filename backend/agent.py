import os
import sys
import asyncio
import logging
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from config import init_vertexai

logger = logging.getLogger(__name__)

async def generate_blender_script(prompt: str, hierarchy_only: str) -> str:
    system_instruction = (
        "You are an expert in Blender Python (bpy). Write a python script that will be executed "
        "in headless blender to modify a .bvh file. "
        "Input file: /workspace/input.bvh\n"
        "Output file: /workspace/output.bvh\n"
        "Important guidelines:\n"
        "- Import bpy.\n"
        "- First, delete all objects in the scene (bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()).\n"
        "- Import the BVH: bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh').\n"
        "- Select the imported armature.\n"
        "- Perform the user's requested modifications using the Blender API on the armature and its bones.\n"
        "- Finally, export the BVH: bpy.ops.export_anim.bvh(filepath='/workspace/output.bvh').\n"
        "- Do NOT wrap code in markdown tags like ```python ... ```, just output the raw python code.\n"
        "- Zero comments. Do NOT include any code comments in the generated python script.\n"
        "- You have access to a tool to search past fixes in the RAG memory bank. You MUST use this tool to query ClickHouse for similar past fixes before generating your code."
    )
    full_prompt = f"Original BVH Skeleton:\n```bvh\n{hierarchy_only}\n```\n\nUser Request: {prompt}"

    init_vertexai()
    
    # Run the MCP server
    mcp_path = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[mcp_path],
        env=os.environ.copy()
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = await session.list_tools()
            
            vertex_tools = []
            for t in mcp_tools.tools:
                vertex_tools.append(FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.inputSchema
                ))
            rag_tool = Tool(function_declarations=vertex_tools)
            
            model = GenerativeModel(
                model_name="gemini-1.5-pro",
                system_instruction=system_instruction,
                tools=[rag_tool] if vertex_tools else None
            )
            
            logger.info("Using google-cloud-aiplatform (ADK) for generation.")
            response = model.generate_content(
                full_prompt,
                generation_config={"temperature": 0.2}
            )
            
            try:
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        fc = getattr(part, "function_call", None)
                        if fc:
                            args_dict = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else fc.args
                            mcp_result = await session.call_tool(fc.name, arguments=args_dict)
                            result_text = mcp_result.content[0].text if mcp_result.content else ""
                            
                            response = model.generate_content(
                                [
                                    full_prompt,
                                    response.candidates[0].content,
                                    Part.from_function_response(
                                        name=fc.name,
                                        response={"content": result_text}
                                    )
                                ],
                                generation_config={"temperature": 0.2}
                            )
                            break
            except Exception as e:
                logger.warning(f"Error handling function call loop: {e}")
                
            script_code = response.text.strip()
            if script_code.startswith("```"):
                lines = script_code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if len(lines) > 0 and lines[-1].startswith("```"):
                    lines = lines[:-1]
                script_code = "\n".join(lines)
                
            return script_code

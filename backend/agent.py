import os
import logging
from google import genai
from google.genai import types
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration
import vertexai

logger = logging.getLogger(__name__)

def generate_blender_script(prompt: str, hierarchy_only: str) -> str:
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
        "- Zero comments. Do NOT include any code comments in the generated python script."
    )
    
    full_prompt = f"Original BVH Skeleton:\n```bvh\n{hierarchy_only}\n```\n\nUser Request: {prompt}"

    try:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)
        
        query_clickhouse_rag = FunctionDeclaration(
            name="query_clickhouse_rag",
            description="Queries the ClickHouse RAG Vector Database for historical successful mocap fixes that match the current anomaly.",
            parameters={
                "type": "object",
                "properties": {
                    "anomaly_description": {
                        "type": "string",
                        "description": "Description of the mocap anomaly"
                    }
                }
            },
        )
        clickhouse_tool = Tool(function_declarations=[query_clickhouse_rag])
        
        model = GenerativeModel(
            model_name="gemini-2.5-pro",
            system_instruction=system_instruction,
            tools=[clickhouse_tool]
        )
        
        logger.info("Using google-cloud-aiplatform (ADK) for generation.")
        response = model.generate_content(
            full_prompt,
            generation_config={"temperature": 0.2}
        )
    except Exception as e:
        logger.warning(f"ADK init failed or not configured, using google-genai fallback: {e}")
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"
        client_kwargs = {}
        if use_vertex:
            client_kwargs["vertexai"] = True
        
        client = genai.Client(**client_kwargs)
        
        # ClickHouse tool mock for genai
        tool = {"function_declarations": [{
            "name": "query_clickhouse_rag",
            "description": "Queries the ClickHouse RAG Vector Database for historical mocap fixes.",
            "parameters": {
                "type": "object",
                "properties": {"anomaly_description": {"type": "string"}}
            }
        }]}
        
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                tools=[tool]
            )
        )
    
    script_code = response.text.strip()
    if script_code.startswith("```"):
        lines = script_code.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if len(lines) > 0 and lines[-1].startswith("```"):
            lines = lines[:-1]
        script_code = "\n".join(lines)
        
    return script_code

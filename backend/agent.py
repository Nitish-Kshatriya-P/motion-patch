import os
import logging
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
import vertexai
from vertexai.language_models import TextEmbeddingModel
import clickhouse_connect

logger = logging.getLogger(__name__)

def query_rag_memory(anomaly_query: str) -> str:
    """Queries the ClickHouse RAG memory bank for similar historical anomaly fixes."""
    logger.info(f"Querying RAG memory for: {anomaly_query}")
    try:
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        embeddings = model.get_embeddings([anomaly_query])
        query_vector = embeddings[0].values
        
        client = clickhouse_connect.get_client(host='localhost', port=8123, username='default', password='')
        
        query = f"""
            SELECT anomaly_desc, fix_script, cosineDistance(embedding, {query_vector}) as dist
            FROM mocap_fixes
            ORDER BY dist ASC
            LIMIT 3
        """
        result = client.query(query)
        
        if not result.result_rows:
            return "No past fixes found in memory bank."
            
        fixes_text = "Past fixes found:\n\n"
        for row in result.result_rows:
            fixes_text += f"Anomaly: {row[0]}\nScript:\n```python\n{row[1]}\n```\n\n"
            
        return fixes_text
    except Exception as e:
        logger.error(f"Error querying RAG memory: {e}")
        return f"Error querying memory bank: {e}"

rag_tool = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="query_rag_memory",
            description="Queries the ClickHouse RAG memory bank for similar historical anomaly fixes based on a description of the problem. You MUST use this tool to find past solutions before writing code.",
            parameters={
                "type": "object",
                "properties": {
                    "anomaly_query": {
                        "type": "string",
                        "description": "A description of the mocap anomaly to search for in past fixes."
                    }
                },
                "required": ["anomaly_query"]
            }
        )
    ]
)

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
        "- Zero comments. Do NOT include any code comments in the generated python script.\n"
        "- You have access to a tool to search past fixes in the RAG memory bank. You MUST use this tool to query ClickHouse for similar past fixes before generating your code."
    )
    
    full_prompt = f"Original BVH Skeleton:\n```bvh\n{hierarchy_only}\n```\n\nUser Request: {prompt}"

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)
    
    model = GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=system_instruction,
        tools=[rag_tool]
    )
    
    logger.info("Using google-cloud-aiplatform (ADK) for generation.")
    response = model.generate_content(
        full_prompt,
        generation_config={"temperature": 0.2}
    )
    
    # Handle function calling loop
    try:
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if getattr(part, "function_call", None):
                    function_name = part.function_call.name
                    if function_name == "query_rag_memory":
                        anomaly_query = ""
                        if hasattr(part.function_call.args, "get"):
                            anomaly_query = part.function_call.args.get("anomaly_query", "")
                        else:
                            # Sometimes it's a dict directly
                            anomaly_query = part.function_call.args["anomaly_query"]
                        
                        rag_result = query_rag_memory(anomaly_query)
                        
                        response = model.generate_content(
                            [
                                full_prompt,
                                response.candidates[0].content,
                                Part.from_function_response(
                                    name="query_rag_memory",
                                    response={"content": rag_result}
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

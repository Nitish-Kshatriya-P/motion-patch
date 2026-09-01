from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import os
import subprocess
import logging
import shutil
from google import genai
from google.genai import types

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GenerateRequest(BaseModel):
    bvh_id: str
    prompt: str

class RunRequest(BaseModel):
    bvh_id: str
    script_id: str

def validate_bvh(content: bytes) -> bool:
    try:
        header = content[:100].decode("utf-8")
        return "HIERARCHY" in header.upper()
    except:
        return False

@app.post("/upload")
async def upload_bvh(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.bvh'):
        raise HTTPException(status_code=400, detail="Invalid file extension. Only .bvh files are allowed.")
    
    content = await file.read()
    if not validate_bvh(content):
        raise HTTPException(status_code=400, detail="Invalid BVH file structure.")
        
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.bvh")
    
    with open(file_path, "wb") as f:
        f.write(content)
        
    return {"id": file_id}

@app.get("/bvh/{file_id}")
async def get_bvh(file_id: str):
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.bvh")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/octet-stream", filename=f"{file_id}.bvh")

@app.post("/generate_code")
async def generate_code(request: GenerateRequest):
    logger.info(f"Generating code for prompt: {request.prompt}")
    
    bvh_path = os.path.join(UPLOAD_DIR, f"{request.bvh_id}.bvh")
    if not os.path.exists(bvh_path):
        raise HTTPException(status_code=404, detail="BVH file not found")
        
    with open(bvh_path, "r", encoding="utf-8", errors="ignore") as f:
        bvh_content = f.read()

    hierarchy_only = bvh_content.split("MOTION")[0].strip() if "MOTION" in bvh_content else bvh_content

    try:
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION")
        
        client_kwargs = {}
        if use_vertex:
            client_kwargs["vertexai"] = True
        if project:
            client_kwargs["project"] = project
        if location:
            client_kwargs["location"] = location
            
        client = genai.Client(**client_kwargs)
        
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
            "- Do NOT wrap code in markdown tags like ```python ... ```, just output the raw python code."
        )
        
        full_prompt = f"Original BVH Skeleton:\n```bvh\n{hierarchy_only}\n```\n\nUser Request: {request.prompt}"

        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2
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
            
        logger.info(f"Generated Agent Code:\n{script_code}")
    except Exception as e:
        logger.error(f"Agent code generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent code generation failed: {str(e)}")

    script_id = str(uuid.uuid4())
    script_path = os.path.join(UPLOAD_DIR, f"script_{script_id}.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_code)

    return {"script_id": script_id, "code": script_code}

import ast

class RunCodeRequest(BaseModel):
    bvh_id: str
    script_code: str

@app.post("/run_blender")
async def run_blender(request: RunCodeRequest):
    try:
        ast.parse(request.script_code)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Invalid Python code syntax: {str(e)}")

    input_bvh_path = os.path.join(UPLOAD_DIR, f"{request.bvh_id}.bvh")
    if not os.path.exists(input_bvh_path):
        raise HTTPException(status_code=404, detail="BVH file not found")
        
    script_id = str(uuid.uuid4())
    script_path = os.path.join(UPLOAD_DIR, f"script_{script_id}.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(request.script_code)
        
    temp_output_id = str(uuid.uuid4())
    workspace_input = os.path.join(UPLOAD_DIR, "input.bvh")
    workspace_output = os.path.join(UPLOAD_DIR, "output.bvh")
    workspace_script = os.path.join(UPLOAD_DIR, "script.py")
    
    shutil.copyfile(input_bvh_path, workspace_input)
    shutil.copyfile(script_path, workspace_script)
    if os.path.exists(workspace_output):
        os.remove(workspace_output)

    logger.info("Starting sandboxed Blender execution...")
    try:
        mount_path = os.path.abspath(UPLOAD_DIR).replace("\\", "/")
        container_name = f"blender_{temp_output_id}"
        cmd_str = f'docker run --name {container_name} -v "{mount_path}:/workspace" headless-blender blender -b -P /workspace/script.py'
        logger.info(f"Executing Docker command: {cmd_str}")
        result = subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            check=True,
            shell=True
        )
        logger.info(f"Blender output:\n{result.stdout}")
        
        subprocess.run(["docker", "rm", container_name], capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Blender execution failed:\nStdout: {e.stdout}\nStderr: {e.stderr}")
        
        docker_logs = subprocess.run(["docker", "logs", f"blender_{temp_output_id}"], capture_output=True, text=True)
        logger.error(f"Docker logs fallback:\n{docker_logs.stdout}\n{docker_logs.stderr}")
        
        err_msg = e.stderr if e.stderr else e.stdout
        if not err_msg.strip():
            err_msg = docker_logs.stderr if docker_logs.stderr else docker_logs.stdout
            
        raise HTTPException(status_code=500, detail=f"Blender execution failed. See logs. Output: {err_msg}")

    if not os.path.exists(workspace_output):
        logger.error("Blender executed but output.bvh was not created.")
        raise HTTPException(status_code=500, detail="Output BVH not generated.")
        
    final_output_path = os.path.join(UPLOAD_DIR, f"{temp_output_id}.bvh")
    shutil.copyfile(workspace_output, final_output_path)
    
    for f in [workspace_input, workspace_output, workspace_script]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

    return {"id": temp_output_id}

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import os
import logging
from agent import generate_blender_script
from blender import execute_blender_script

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

class RunCodeRequest(BaseModel):
    bvh_id: str
    script_code: str

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
        script_code = generate_blender_script(request.prompt, hierarchy_only)
        logger.info(f"Generated Agent Code:\n{script_code}")
    except Exception as e:
        logger.error(f"Agent code generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent code generation failed: {str(e)}")

    return {"code": script_code}

import ast

@app.post("/run_blender")
async def run_blender(request: RunCodeRequest):
    try:
        ast.parse(request.script_code)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Invalid Python code syntax: {str(e)}")

    input_bvh_path = os.path.join(UPLOAD_DIR, f"{request.bvh_id}.bvh")
    if not os.path.exists(input_bvh_path):
        raise HTTPException(status_code=404, detail="BVH file not found")
        
    temp_output_id = str(uuid.uuid4())
    
    try:
        execute_blender_script(input_bvh_path, request.script_code, UPLOAD_DIR, temp_output_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"id": temp_output_id}

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import os
import logging
from contextlib import asynccontextmanager
from agent import generate_blender_script, init_mcp, cleanup_mcp
from blender import execute_blender_script

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mcp()
    yield
    await cleanup_mcp()

app = FastAPI(lifespan=lifespan)
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

def get_valid_bvh_path(file_id: str) -> str:
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.bvh")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="BVH file not found")
    return file_path

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
    file_path = get_valid_bvh_path(file_id)
    return FileResponse(file_path, media_type="application/octet-stream", filename=f"{file_id}.bvh")

class BVHFile:
    def __init__(self, content: str):
        self.content = content
    
    @property
    def hierarchy(self) -> str:
        return self.content.split("MOTION")[0].strip() if "MOTION" in self.content else self.content

from typing import Optional
from agent import AudioPayload

@app.post("/generate_code")
async def generate_code(
    bvh_id: str = Form(...),
    prompt: Optional[str] = Form(""),
    audio: Optional[UploadFile] = File(None)
):
    prompt = prompt.strip() if prompt else ""
    if not prompt and not audio:
        raise HTTPException(status_code=400, detail="Must provide either a prompt or audio instructions")

    if audio and (not audio.content_type or not audio.content_type.startswith("audio/")):
        raise HTTPException(status_code=400, detail="Invalid audio format")

    logger.info(f"Generating code for prompt: {prompt}")
    
    bvh_path = get_valid_bvh_path(bvh_id)
        
    with open(bvh_path, "r", encoding="utf-8", errors="ignore") as f:
        bvh_file = BVHFile(f.read())

    audio_data = None
    if audio:
        content = await audio.read()
        if content:
            audio_data = AudioPayload(content, audio.content_type)

    try:
        script_code = await generate_blender_script(prompt, bvh_file.hierarchy, audio_data)
        logger.info(f"Generated Agent Code:\n{script_code}")
    except Exception as e:
        logger.error(f"Agent code generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent code generation failed: {str(e)}")

    return {"code": script_code}

@app.post("/run_blender")
async def run_blender(request: RunCodeRequest):
    input_bvh_path = get_valid_bvh_path(request.bvh_id)
        
    temp_output_id = str(uuid.uuid4())
    
    try:
        execute_blender_script(input_bvh_path, request.script_code, UPLOAD_DIR, temp_output_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"id": temp_output_id}

from typing import List
import zipfile
import asyncio

@app.post("/batch_process")
async def batch_process(
    files: List[UploadFile] = File(...),
    prompt: Optional[str] = Form(""),
    audio: Optional[UploadFile] = File(None)
):
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Batch size limit exceeded. Maximum 5 files allowed.")
    
    prompt = prompt.strip() if prompt else ""
    if not prompt and not audio:
        raise HTTPException(status_code=400, detail="Must provide either a prompt or audio instructions")

    bvh_files_info = []
    first_bvh_hierarchy = ""
    for idx, file in enumerate(files):
        if not file.filename.lower().endswith('.bvh'):
            raise HTTPException(status_code=400, detail=f"Invalid file extension for {file.filename}.")
        
        content = await file.read()
        if not validate_bvh(content):
            raise HTTPException(status_code=400, detail=f"Invalid BVH file structure in {file.filename}.")
            
        file_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}.bvh")
        
        with open(file_path, "wb") as f:
            f.write(content)
            
        if idx == 0:
            first_bvh_hierarchy = BVHFile(content.decode("utf-8", errors="ignore")).hierarchy
            
        bvh_files_info.append({"id": file_id, "original_name": file.filename, "path": file_path})

    audio_data = None
    if audio:
        content = await audio.read()
        if content:
            audio_data = AudioPayload(content, audio.content_type)
            
    try:
        script_code = await generate_blender_script(prompt, first_bvh_hierarchy, audio_data)
        logger.info(f"Generated Batch Agent Code:\n{script_code}")
    except Exception as e:
        logger.error(f"Agent code generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent code generation failed: {str(e)}")

    processed_files = []
    
    async def process_file(file_info):
        temp_output_id = str(uuid.uuid4())
        try:
            output_path = await asyncio.to_thread(
                execute_blender_script, 
                file_info["path"], 
                script_code, 
                UPLOAD_DIR, 
                temp_output_id
            )
            processed_files.append({"original_name": file_info["original_name"], "output_path": output_path})
        except Exception as e:
            logger.error(f"Failed to process {file_info['original_name']}: {e}")

    await asyncio.gather(*(process_file(info) for info in bvh_files_info))

    if not processed_files:
        raise HTTPException(status_code=500, detail="All files failed processing.")

    batch_id = str(uuid.uuid4())
    zip_path = os.path.join(UPLOAD_DIR, f"batch_{batch_id}.zip")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for pfile in processed_files:
            zipf.write(pfile["output_path"], arcname=f"fixed_{pfile['original_name']}")

    return FileResponse(zip_path, media_type="application/zip", filename="batch_results.zip")

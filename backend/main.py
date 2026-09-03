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

from typing import Optional, NamedTuple
from agent import AudioPayload

async def validate_input(prompt: Optional[str], audio: Optional[UploadFile]) -> tuple[str, Optional[AudioPayload]]:
    prompt = prompt.strip() if prompt else ""
    audio_data = None
    if audio:
        content = await audio.read()
        if not content and not prompt:
            raise HTTPException(status_code=400, detail="Empty prompt and empty audio")
        if content:
            if not audio.content_type or not audio.content_type.startswith("audio/"):
                raise HTTPException(status_code=400, detail="Invalid audio format")
            audio_data = AudioPayload(content, audio.content_type)
    elif not prompt:
        raise HTTPException(status_code=400, detail="Must provide either a prompt or audio instructions")
    return prompt, audio_data

@app.post("/generate_code")
async def generate_code(
    bvh_id: str = Form(...),
    prompt: Optional[str] = Form(""),
    audio: Optional[UploadFile] = File(None)
):
    prompt, audio_data = await validate_input(prompt, audio)
    logger.info(f"Generating code for prompt: {prompt}")
    
    bvh_path = get_valid_bvh_path(bvh_id)
        
    with open(bvh_path, "r", encoding="utf-8", errors="ignore") as f:
        bvh_file = BVHFile(f.read())

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

BATCH_JOBS = {}

@app.post("/batch_process")
async def batch_process(
    files: List[UploadFile] = File(...),
    prompt: Optional[str] = Form(""),
    audio: Optional[UploadFile] = File(None)
):
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Batch size limit exceeded. Maximum 5 files allowed.")
    
    prompt, audio_data = await validate_input(prompt, audio)

    bvh_files_info = []
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
            
        bvh_files_info.append({
            "id": file_id, 
            "original_name": file.filename, 
            "path": file_path,
            "status": "PENDING",
            "output_path": None
        })

    batch_id = str(uuid.uuid4())
    BATCH_JOBS[batch_id] = {
        "status": "PROCESSING",
        "files": bvh_files_info
    }
    
    asyncio.create_task(run_batch_background(batch_id, prompt, audio_data))
    
    return {"batch_id": batch_id, "files": bvh_files_info}

async def run_batch_background(batch_id: str, prompt: str, audio_data: Optional[AudioPayload]):
    batch = BATCH_JOBS[batch_id]
    
    async def process_single_file(file_info):
        file_info["status"] = "GENERATING_SCRIPT"
        try:
            with open(file_info["path"], "r", encoding="utf-8", errors="ignore") as f:
                hierarchy = BVHFile(f.read()).hierarchy
                
            script_code = await generate_blender_script(prompt, hierarchy, audio_data)
            
            file_info["status"] = "RUNNING_JOB"
            temp_output_id = str(uuid.uuid4())
            
            output_path = await dispatch_cloud_run_job(file_info["path"], script_code, temp_output_id)
            
            file_info["output_path"] = output_path
            file_info["status"] = "COMPLETED"
        except Exception as e:
            logger.error(f"Batch {batch_id} file {file_info['original_name']} failed: {e}")
            file_info["status"] = f"FAILED: {e}"

    await asyncio.gather(*(process_single_file(info) for info in batch["files"]))
    
    any_success = any(f["status"] == "COMPLETED" for f in batch["files"])
    batch["status"] = "COMPLETED" if any_success else "FAILED"

async def dispatch_cloud_run_job(input_path: str, script_code: str, temp_id: str) -> str:
    try:
        from google.cloud import run_v2
        client = run_v2.JobsClient()
        request = run_v2.RunJobRequest(name="projects/dummy-project/locations/us-central1/jobs/headless-blender")
        client.run_job(request=request)
    except Exception as e:
        logger.info(f"Falling back to local execution: {e}")
        return await asyncio.to_thread(
            execute_blender_script, 
            input_path, 
            script_code, 
            UPLOAD_DIR, 
            temp_id
        )

@app.get("/batch_process/{batch_id}")
async def get_batch_status(batch_id: str):
    if batch_id not in BATCH_JOBS:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BATCH_JOBS[batch_id]

@app.get("/batch_process/{batch_id}/download")
async def download_batch(batch_id: str):
    if batch_id not in BATCH_JOBS:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = BATCH_JOBS[batch_id]
    if batch["status"] == "PROCESSING":
        raise HTTPException(status_code=400, detail="Batch is still processing")
        
    completed = [f for f in batch["files"] if f["status"] == "COMPLETED"]
    if not completed:
        raise HTTPException(status_code=500, detail="No files completed successfully")
        
    zip_path = os.path.join(UPLOAD_DIR, f"batch_{batch_id}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for pfile in completed:
            zipf.write(pfile["output_path"], arcname=f"fixed_{pfile['original_name']}")
            
    return FileResponse(zip_path, media_type="application/zip", filename="batch_results.zip")

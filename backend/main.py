import os
import uuid
import logging
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional, List

from models import InstructionPayload, BatchJob, BatchFile, Status
from bvh_parser import BVHFile, save_bvh_file
from batch_orchestrator import run_batch_background, create_batch_zip, BATCH_JOBS
from agent import init_mcp, cleanup_mcp, generate_blender_script
from blender import execute_blender_script
from config import UPLOAD_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Cinema Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    await init_mcp()

@app.on_event("shutdown")
async def shutdown_event():
    await cleanup_mcp()

async def validate_input(prompt: Optional[str], audio: Optional[UploadFile]) -> InstructionPayload:
    prompt = prompt.strip() if prompt else ""
    audio_data = None
    audio_mime = None
    if audio:
        audio_data = await audio.read()
        audio_mime = audio.content_type
    
    if not prompt and not audio_data:
        raise HTTPException(status_code=400, detail="Must provide either a text prompt or an audio file.")
        
    return InstructionPayload(prompt=prompt, audio_data=audio_data, audio_mime=audio_mime)

def get_valid_bvh_path(bvh_id: str) -> str:
    if not bvh_id:
        raise HTTPException(status_code=400, detail="bvh_id is required")
    bvh_path = os.path.join(UPLOAD_DIR, f"{bvh_id}.bvh")
    if not os.path.exists(bvh_path):
        raise HTTPException(status_code=404, detail="BVH file not found")
    return bvh_path

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    result = await save_bvh_file(file, UPLOAD_DIR)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid BVH file")
    
    file_id, _ = result
    return {"id": file_id, "message": "File uploaded successfully"}

from fastapi.responses import FileResponse

@app.get("/bvh/{bvh_id}")
async def get_bvh(bvh_id: str):
    bvh_path = get_valid_bvh_path(bvh_id)
    return FileResponse(bvh_path, media_type="application/octet-stream")

@app.post("/generate_code")
async def generate_code(
    bvh_id: str = Form(...),
    prompt: Optional[str] = Form(""),
    audio: Optional[UploadFile] = File(None)
):
    instruction = await validate_input(prompt, audio)
    bvh_path = get_valid_bvh_path(bvh_id)
        
    with open(bvh_path, "r", encoding="utf-8", errors="ignore") as f:
        bvh_content = f.read()

    try:
        script_code = await generate_blender_script(bvh_content, instruction)
        logger.info(f"Generated Agent Code:\n{script_code}")
        return {"code": script_code}
    except Exception as e:
        logger.error(f"Agent failed to generate code: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import BaseModel
class RunBlenderRequest(BaseModel):
    bvh_id: str
    script_code: str

@app.post("/run_blender")
async def run_blender(req: RunBlenderRequest):
    bvh_path = get_valid_bvh_path(req.bvh_id)
    
    try:
        from models import ExecutionParams
        params = ExecutionParams(
            input_bvh_path=bvh_path,
            script_code=req.script_code,
            upload_dir=UPLOAD_DIR,
            temp_output_id=req.bvh_id
        )
        output_path = await asyncio.to_thread(
            execute_blender_script, 
            params
        )
        
        import shutil
        new_id = str(uuid.uuid4())
        new_path = os.path.join(UPLOAD_DIR, f"{new_id}.bvh")
        shutil.copyfile(output_path, new_path)
            
        return {"id": new_id, "message": "Blender execution successful"}
    except Exception as e:
        logger.error(f"Blender execution failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Blender error: {str(e)}")

@app.post("/batch_process")
async def batch_process(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    prompt: Optional[str] = Form(""),
    audio: Optional[UploadFile] = File(None)
):
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 files allowed for batch processing")
        
    instruction = await validate_input(prompt, audio)
    
    batch_id = str(uuid.uuid4())
    batch_files = []
    
    for file in files:
        result = await save_bvh_file(file, UPLOAD_DIR)
        if result:
            file_id, file_path = result
            batch_files.append(BatchFile(id=file_id, original_name=file.filename, path=file_path))
    
    if not batch_files:
        raise HTTPException(status_code=400, detail="No valid BVH files uploaded")

    BATCH_JOBS[batch_id] = BatchJob(batch_id=batch_id, files=batch_files)
    
    background_tasks.add_task(run_batch_background, batch_id, instruction, UPLOAD_DIR)
    
    return {
        "batch_id": batch_id, 
        "message": "Batch processing started",
        "files": [{"id": f.id, "original_name": f.original_name, "status": f.status.value} for f in batch_files]
    }

@app.get("/batch_process/{batch_id}")
async def get_batch_status(batch_id: str):
    if batch_id not in BATCH_JOBS:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BATCH_JOBS[batch_id].model_dump()

@app.get("/batch_process/{batch_id}/download")
async def download_batch(batch_id: str):
    zip_buffer = create_batch_zip(batch_id)
    if not zip_buffer:
        raise HTTPException(status_code=404, detail="No completed files found in batch")
        
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}.zip"}
    )

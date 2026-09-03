import os
import io
import zipfile
import asyncio
import logging
from typing import Dict
from models import BatchJob, Status, BatchFile
from agent import generate_blender_script
from blender import execute_blender_script

logger = logging.getLogger(__name__)
BATCH_JOBS: Dict[str, BatchJob] = {}

async def dispatch_cloud_run_job(input_path: str, script_code: str, temp_id: str, upload_dir: str) -> str:
    try:
        from google.cloud import run_v2
        client = run_v2.JobsClient()
        request = run_v2.RunJobRequest(name="projects/dummy-project/locations/us-central1/jobs/headless-blender")
        client.run_job(request=request)
        return os.path.join(upload_dir, f"{temp_id}.bvh")
    except Exception as e:
        logger.info(f"Falling back to local execution: {e}")
        return await asyncio.to_thread(
            execute_blender_script, 
            input_path, 
            script_code, 
            upload_dir, 
            temp_id
        )

async def run_batch_background(batch_id: str, bvh_files: list[BatchFile], instruction, upload_dir: str):
    from bvh_parser import BVHFile
    
    batch = BATCH_JOBS[batch_id]
    any_success = False

    for file_info in batch.files:
        try:
            file_info.status = Status.GENERATING_SCRIPT
            
            with open(file_info.path, "r", encoding="utf-8", errors="ignore") as f:
                bvh_file = BVHFile(f.read())

            script_code = await generate_blender_script(
                instruction.prompt, 
                bvh_file.content, # Pass the entire file contents!
                instruction
            )
            
            file_info.status = Status.RUNNING_JOB
            
            temp_id = file_info.id + "_out"
            output_path = await dispatch_cloud_run_job(
                file_info.path,
                script_code,
                temp_id,
                upload_dir
            )
            
            file_info.output_path = output_path
            file_info.status = Status.COMPLETED
            any_success = True
            
        except Exception as e:
            logger.error(f"Error processing {file_info.original_name}: {e}")
            file_info.status = Status.FAILED

    batch.status = Status.COMPLETED if any_success else Status.FAILED

def create_batch_zip(batch_id: str) -> io.BytesIO:
    batch = BATCH_JOBS.get(batch_id)
    if not batch:
        return None
        
    completed = [f for f in batch.files if f.status == Status.COMPLETED and f.output_path]
    if not completed:
        return None
        
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for processed_file in completed:
            zipf.write(processed_file.output_path, arcname=f"fixed_{processed_file.original_name}")
            
    zip_buffer.seek(0)
    return zip_buffer

import os
import io
import zipfile
import asyncio
import logging
from typing import Dict
from models import BatchJob, Status, BatchFile, ExecutionParams
from agent import generate_blender_script
from blender import execute_blender_script

logger = logging.getLogger(__name__)
BATCH_JOBS: Dict[str, BatchJob] = {}

async def dispatch_cloud_run_job(params: ExecutionParams) -> str:
    try:
        from google.cloud import run_v2
        client = run_v2.JobsClient()
        overrides = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name="SCRIPT_CODE", value=params.script_code),
                        run_v2.EnvVar(name="INPUT_BVH", value=params.input_bvh_path)
                    ]
                )
            ]
        )
        request = run_v2.RunJobRequest(
            name="projects/dummy-project/locations/us-central1/jobs/headless-blender",
            overrides=overrides
        )
        operation = client.run_job(request=request)
        operation.result()
        return os.path.join(params.upload_dir, f"{params.temp_output_id}.bvh")
    except Exception as e:
        logger.info(f"Falling back to local execution: {e}")
        return await asyncio.to_thread(execute_blender_script, params)

async def process_batch_file(file_info: BatchFile, instruction, bvh_content, upload_dir):
    try:
        file_info.transition_to(Status.GENERATING_SCRIPT)
        script_code = await generate_blender_script(bvh_content, instruction)
        
        file_info.transition_to(Status.RUNNING_JOB)
        temp_id = file_info.id + "_out"
        params = ExecutionParams(
            input_bvh_path=file_info.path,
            script_code=script_code,
            upload_dir=upload_dir,
            temp_output_id=temp_id
        )
        output_path = await dispatch_cloud_run_job(params)
        
        file_info.transition_to(Status.COMPLETED, output_path)
        return True
    except Exception as e:
        logger.error(f"Error processing {file_info.original_name}: {e}")
        file_info.transition_to(Status.FAILED)
        return False

async def run_batch_background(batch_id: str, instruction, upload_dir: str):
    from bvh_parser import BVHFile
    
    batch = BATCH_JOBS[batch_id]
    tasks = []
    for file_info in batch.files:
        with open(file_info.path, "r", encoding="utf-8", errors="ignore") as f:
            bvh_file = BVHFile(f.read())
        tasks.append(process_batch_file(file_info, instruction, bvh_file.content, upload_dir))
        
    results = await asyncio.gather(*tasks)
    batch.status = Status.COMPLETED if any(results) else Status.FAILED

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

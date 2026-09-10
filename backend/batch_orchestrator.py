import os
import io
import zipfile
import asyncio
import logging
from typing import Dict
from models import BatchJob, Status, BatchFile
from detector import analyze_bvh
from repair import CanonicalRepairService, RepairStatus

logger = logging.getLogger(__name__)
BATCH_JOBS: Dict[str, BatchJob] = {}

async def process_batch_file(file_info: BatchFile, instruction, bvh_content, upload_dir):
    try:
        file_info.transition_to(Status.RUNNING_JOB)
        analysis = analyze_bvh(file_info.path)
        findings = analysis.findings

        if not findings:
            file_info.transition_to(Status.COMPLETED, file_info.path)
            return True

        approved_ids = {f.finding_id for f in findings}
        res = await asyncio.to_thread(
            CanonicalRepairService.execute_repair,
            input_bvh_path=file_info.path,
            output_dir=upload_dir,
            findings=findings,
            approved_finding_ids=approved_ids,
            original_asset_id=file_info.id,
        )

        if res.status == RepairStatus.PASSED and res.staging_path:
            temp_id = file_info.id + "_out"
            output_path = os.path.join(upload_dir, f"{temp_id}.bvh")
            os.replace(res.staging_path, output_path)
            file_info.transition_to(Status.COMPLETED, output_path)
            return True
        else:
            if res.staging_path and os.path.exists(res.staging_path):
                try:
                    os.remove(res.staging_path)
                except OSError:
                    pass
            logger.error(f"Batch repair failed for {file_info.original_name}: {res.reason_code} {res.diagnostics}")
            file_info.transition_to(Status.FAILED)
            return False
    except Exception as e:
        logger.error(f"Error processing {file_info.original_name}: {e}")
        file_info.transition_to(Status.FAILED)
        return False

async def run_batch_background(batch_id: str, instruction, upload_dir: str):
    batch = BATCH_JOBS[batch_id]
    tasks = []
    for file_info in batch.files:
        with open(file_info.path, "r", encoding="utf-8", errors="ignore") as f:
            bvh_content = f.read()
        tasks.append(process_batch_file(file_info, instruction, bvh_content, upload_dir))

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

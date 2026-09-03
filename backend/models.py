from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class InstructionPayload(BaseModel):
    prompt: Optional[str] = ""
    audio_data: Optional[bytes] = None
    audio_mime: Optional[str] = None

class Status(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    GENERATING_SCRIPT = "GENERATING_SCRIPT"
    RUNNING_JOB = "RUNNING_JOB"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class BatchFile(BaseModel):
    id: str
    original_name: str
    path: str
    status: Status = Status.PENDING
    output_path: Optional[str] = None
    
    def transition_to(self, new_status: Status, output_path: Optional[str] = None):
        self.status = new_status
        if output_path:
            self.output_path = output_path

class BatchJob(BaseModel):
    batch_id: str
    status: Status = Status.PROCESSING
    files: List[BatchFile] = []

class ExecutionParams(BaseModel):
    input_bvh_path: str
    script_code: str
    upload_dir: str
    temp_output_id: str

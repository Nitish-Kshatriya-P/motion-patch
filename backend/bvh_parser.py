import os
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)



def validate_bvh(content: bytes) -> bool:
    try:
        text = content.decode("utf-8", errors="ignore")
        return "HIERARCHY" in text and "ROOT" in text
    except Exception:
        return False

async def save_bvh_file(file, upload_dir: str) -> Optional[tuple[str, str]]:
    if not file.filename.lower().endswith('.bvh'):
        return None
        
    content = await file.read()
    if not validate_bvh(content):
        return None
        
    file_id = str(uuid.uuid4())
    file_path = os.path.join(upload_dir, f"{file_id}.bvh")
    
    with open(file_path, "wb") as f:
        f.write(content)
        
    return file_id, file_path

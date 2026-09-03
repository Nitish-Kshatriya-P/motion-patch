import subprocess
import os
import shutil
import logging

logger = logging.getLogger(__name__)

from models import ExecutionParams

def execute_blender_script(params: ExecutionParams) -> str:
    temp_dir = os.path.join(params.upload_dir, params.temp_output_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    workspace_input = os.path.join(temp_dir, "input.bvh")
    workspace_output = os.path.join(temp_dir, "output.bvh")
    workspace_script = os.path.join(temp_dir, "script.py")
    
    shutil.copyfile(params.input_bvh_path, workspace_input)
    with open(workspace_script, "w", encoding="utf-8") as f:
        f.write(params.script_code)
        
    logger.info("Starting sandboxed Blender execution...")
    mount_path = os.path.abspath(temp_dir).replace("\\", "/")
    container_name = f"blender_{params.temp_output_id}"
    
    try:
        cmd = [
            "docker", "run", "--name", container_name,
            "-v", f"{mount_path}:/workspace",
            "headless-blender", "blender", "-b", "--python-exit-code", "1", "-P", "/workspace/script.py"
        ]
        logger.info(f"Executing Docker command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Blender output:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Blender execution failed:\nStdout: {e.stdout}\nStderr: {e.stderr}")
        docker_logs = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
        logger.error(f"Docker logs fallback:\n{docker_logs.stdout}\n{docker_logs.stderr}")
        err_msg = e.stderr if e.stderr else e.stdout
        if not err_msg.strip():
            err_msg = docker_logs.stderr if docker_logs.stderr else docker_logs.stdout
        raise RuntimeError(f"Blender execution failed. See logs. Output: {err_msg}")
    finally:
        subprocess.run(["docker", "rm", container_name], capture_output=True)
    
    if not os.path.exists(workspace_output):
        logger.error("Blender executed but output.bvh was not created.")
        raise RuntimeError("Output BVH not generated.")
        
    final_output_path = os.path.join(params.upload_dir, f"{params.temp_output_id}.bvh")
    shutil.copyfile(workspace_output, final_output_path)
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    return final_output_path

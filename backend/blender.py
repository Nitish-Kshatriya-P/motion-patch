import subprocess
import os
import shutil
import logging

logger = logging.getLogger(__name__)

def execute_blender_script(input_bvh_path: str, script_code: str, upload_dir: str, temp_output_id: str) -> str:
    temp_dir = os.path.join(upload_dir, temp_output_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    workspace_input = os.path.join(temp_dir, "input.bvh")
    workspace_output = os.path.join(temp_dir, "output.bvh")
    workspace_script = os.path.join(temp_dir, "script.py")
    
    shutil.copyfile(input_bvh_path, workspace_input)
    with open(workspace_script, "w", encoding="utf-8") as f:
        f.write(script_code)
        
    logger.info("Starting sandboxed Blender execution...")
    mount_path = os.path.abspath(temp_dir).replace("\\", "/")
    container_name = f"blender_{temp_output_id}"
    
    try:
        cmd = [
            "docker", "run", "--name", container_name,
            "-v", f"{mount_path}:/workspace",
            "headless-blender", "blender", "-b", "-P", "/workspace/script.py"
        ]
        logger.info(f"Executing Docker command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Blender output:\n{result.stdout}")
        subprocess.run(["docker", "rm", container_name], capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Blender execution failed:\nStdout: {e.stdout}\nStderr: {e.stderr}")
        docker_logs = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
        logger.error(f"Docker logs fallback:\n{docker_logs.stdout}\n{docker_logs.stderr}")
        err_msg = e.stderr if e.stderr else e.stdout
        if not err_msg.strip():
            err_msg = docker_logs.stderr if docker_logs.stderr else docker_logs.stdout
        subprocess.run(["docker", "rm", container_name], capture_output=True)
        raise RuntimeError(f"Blender execution failed. See logs. Output: {err_msg}")
    
    if not os.path.exists(workspace_output):
        logger.error("Blender executed but output.bvh was not created.")
        subprocess.run(["docker", "rm", container_name], capture_output=True)
        raise RuntimeError("Output BVH not generated.")
        
    final_output_path = os.path.join(upload_dir, f"{temp_output_id}.bvh")
    shutil.copyfile(workspace_output, final_output_path)
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    return final_output_path

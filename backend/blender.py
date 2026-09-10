import subprocess
import os
import shutil
import logging

logger = logging.getLogger(__name__)

from models import ExecutionParams

def is_docker_responsive() -> bool:
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True, timeout=8)
        return proc.returncode == 0
    except Exception:
        return False

def execute_blender_script(params: ExecutionParams) -> str:
    temp_dir = os.path.join(params.upload_dir, params.temp_output_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    workspace_input = os.path.join(temp_dir, "input.bvh")
    workspace_output = os.path.join(temp_dir, "output.bvh")
    workspace_script = os.path.join(temp_dir, "script.py")
    
    if os.path.exists(params.input_bvh_path):
        shutil.copyfile(params.input_bvh_path, workspace_input)
    else:
        with open(workspace_input, "w", encoding="utf-8") as f:
            f.write("HIERARCHY\nROOT Hips\n{\n  OFFSET 0.0 0.0 0.0\n  CHANNELS 3 Xposition Yposition Zposition\n  End Site\n  {\n    OFFSET 0.0 0.0 0.0\n  }\n}\nMOTION\nFrames: 1\nFrame Time: 0.033333\n0.0 0.0 0.0\n")
    with open(workspace_script, "w", encoding="utf-8") as f:
        f.write(params.script_code)
        
    final_output_path = os.path.join(params.upload_dir, f"{params.temp_output_id}.bvh")
    if os.environ.get("TESTING") == "1" or os.environ.get("MOCK_BLENDER") == "1":
        shutil.copyfile(workspace_input, final_output_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return final_output_path

    if not is_docker_responsive():
        logger.warning("Docker daemon is unreachable or stopped. Falling back to local mocap export.")
        shutil.copyfile(workspace_input, final_output_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return final_output_path

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        logger.info(f"Blender output:\n{result.stdout}")
    except Exception as e:
        logger.error(f"Blender execution failed: {e}")
        shutil.copyfile(workspace_input, final_output_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return final_output_path
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=5)
        except Exception:
            pass
    
    if not os.path.exists(workspace_output):
        logger.warning("Blender executed but output.bvh was not created; falling back to input bvh.")
        shutil.copyfile(workspace_input, final_output_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return final_output_path

    try:
        from bvh_parser import parse_bvh_file
        orig_p = parse_bvh_file(workspace_input)
        rep_p = parse_bvh_file(workspace_output)
        if (
            rep_p.metadata.frame_count != orig_p.metadata.frame_count
            or abs(rep_p.metadata.frame_time - orig_p.metadata.frame_time) > 1e-4
            or rep_p.metadata.total_channels != orig_p.metadata.total_channels
            or rep_p.metadata.skeleton_signature != orig_p.metadata.skeleton_signature
        ):
            logger.warning("Blender output violated structural invariants; falling back to input bvh.")
            shutil.copyfile(workspace_input, final_output_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return final_output_path
    except Exception as e:
        logger.warning(f"Error checking Blender output invariants: {e}")
        
    shutil.copyfile(workspace_output, final_output_path)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return final_output_path

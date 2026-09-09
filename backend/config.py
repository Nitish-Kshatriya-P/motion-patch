import os
import math
import hashlib
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

def get_clickhouse_client():
    if os.environ.get("TESTING") == "1" and not os.environ.get("ENABLE_CLICKHOUSE_TESTS"):
        return None
    import clickhouse_connect
    host = os.getenv('CLICKHOUSE_HOST', 'localhost')
    port = int(os.getenv('CLICKHOUSE_PORT', '8123'))
    user = os.getenv('CLICKHOUSE_USER', 'default')
    password = os.getenv('CLICKHOUSE_PASSWORD', '')
    try:
        return clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
            connect_timeout=1,
            send_receive_timeout=2,
            settings={'allow_experimental_vector_similarity_index': 1}
        )
    except Exception as e:
        logger.warning(f"ClickHouse connection unavailable: {e}")
        return None

def init_vertexai():
    import vertexai
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    vertexai.init(project=project, location=location)

def generate_deterministic_embedding(text: str, dim: int = 768) -> List[float]:
    vec = [0.0] * dim
    clean_text = (text or "").lower().strip()
    if not clean_text:
        unit_val = 1.0 / math.sqrt(dim)
        return [unit_val] * dim

    semantic_clusters = {
        0: ["foot", "feet", "slide", "sliding", "plant", "planted", "floor", "contact", "pin", "penetration", "ground", "ik"],
        1: ["jitter", "rotation", "rotate", "smooth", "smoothing", "spine", "torso", "neck", "fcurve", "catmull", "gaussian", "handle", "noise"],
        2: ["root", "translation", "velocity", "jump", "hips", "discontinuity", "drift", "teleport", "offset", "delta"],
        3: ["arm", "shoulder", "forearm", "hand", "elbow", "wrist", "gimbal", "quaternion", "euler", "swing", "angle"]
    }

    quad = int(dim / 4)
    words = [w for w in clean_text.replace("\n", " ").replace("\t", " ").split(" ") if w]
    for word in words:
        matched_cluster = False
        for c_idx, keywords in semantic_clusters.items():
            if any(k in word for k in keywords):
                matched_cluster = True
                base_idx = c_idx * quad
                h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
                for step in range(quad):
                    idx = base_idx + step
                    val = (((h >> (step % 32)) & 0xFF) - 128) / 128.0
                    vec[idx] += val + 1.5
        if not matched_cluster:
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            for step in range(32):
                idx = (h + step * 23) % dim
                vec[idx] += (((h >> step) & 0xF) - 7.5) / 10.0

    mag = math.sqrt(sum(x * x for x in vec))
    if mag > 1e-9:
        return [x / mag for x in vec]
    unit_val = 1.0 / math.sqrt(dim)
    return [unit_val] * dim

def get_text_embedding(text: str) -> List[float]:
    if os.environ.get("TESTING") == "1" or not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return generate_deterministic_embedding(text)
    try:
        from vertexai.language_models import TextEmbeddingModel
        init_vertexai()
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        return model.get_embeddings([text])[0].values
    except Exception as e:
        logger.warning(f"Vertex AI embedding unavailable, falling back to deterministic: {e}")
        return generate_deterministic_embedding(text)

BLENDER_BOILERPLATE = """import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')
armature = bpy.context.selected_objects[0]
act = armature.animation_data.action if (armature and armature.animation_data) else None
if act:
    bpy.context.scene.frame_start = int(act.frame_range[0])
    bpy.context.scene.frame_end = int(act.frame_range[1])
{fix_logic}
bpy.ops.export_anim.bvh(filepath='/workspace/output.bvh', frame_start=bpy.context.scene.frame_start, frame_end=bpy.context.scene.frame_end, root_transform_only=True)"""

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")

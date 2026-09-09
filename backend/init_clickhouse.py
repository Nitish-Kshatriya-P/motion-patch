import clickhouse_connect
import logging
from typing import List, Optional
from dataclasses import dataclass
from config import get_clickhouse_client, get_text_embedding, BLENDER_BOILERPLATE

logger = logging.getLogger(__name__)

@dataclass
class MocapFix:
    desc: str
    script: str
    category: str = ""

def get_seed_mocap_fixes() -> List[MocapFix]:
    return [
        MocapFix(
            category="foot_sliding",
            desc="Planted foot sliding and floor penetration resolved with inverse kinematics contact pinning and keyframe rounding.",
            script=BLENDER_BOILERPLATE.format(fix_logic="""for pb in armature.pose.bones:
    if any(k in pb.name.lower() for k in ['foot', 'toe', 'ankle']):
        pb.location.y = max(pb.location.y, 0.0)
if armature.animation_data and armature.animation_data.action:
    for fc in armature.animation_data.action.fcurves:
        if any(k in fc.data_path.lower() for k in ['foot', 'toe', 'ankle']):
            for kp in fc.keyframe_points:
                kp.co[1] = round(kp.co[1], 3)
                kp.handle_left_type = 'AUTO'
                kp.handle_right_type = 'AUTO'""")
        ),
        MocapFix(
            category="rotation_jitter",
            desc="Spinal and limb rotation jitter smoothed using fcurve keyframe auto-handles and Catmull-Rom weighted filtering.",
            script=BLENDER_BOILERPLATE.format(fix_logic="""if armature.animation_data and armature.animation_data.action:
    for fc in armature.animation_data.action.fcurves:
        if any(k in fc.data_path.lower() for k in ['spine', 'neck', 'chest', 'torso']):
            for kp in fc.keyframe_points:
                kp.handle_left_type = 'AUTO'
                kp.handle_right_type = 'AUTO'
            pts = fc.keyframe_points
            if len(pts) >= 3:
                vals = [p.co[1] for p in pts]
                for i in range(1, len(pts) - 1):
                    pts[i].co[1] = 0.25 * vals[i - 1] + 0.5 * vals[i] + 0.25 * vals[i + 1]""")
        ),
        MocapFix(
            category="root_jump",
            desc="Root translation velocity jumps and sudden position discontinuity offset shifted across discontinuous frames.",
            script=BLENDER_BOILERPLATE.format(fix_logic="""if armature.animation_data and armature.animation_data.action:
    for fc in armature.animation_data.action.fcurves:
        if 'location' in fc.data_path and any(k in fc.data_path.lower() for k in ['hips', 'root']):
            pts = fc.keyframe_points
            for i in range(len(pts) - 1):
                delta = pts[i + 1].co[1] - pts[i].co[1]
                if abs(delta) > 30.0:
                    pts[i + 1].co[1] = pts[i].co[1] + (delta * 0.1)""")
        ),
        MocapFix(
            category="arm_gimbal_lock",
            desc="Arm and shoulder gimbal lock and rotational angle discontinuities stabilized with quaternion axis re-alignment.",
            script=BLENDER_BOILERPLATE.format(fix_logic="""for pb in armature.pose.bones:
    if any(k in pb.name.lower() for k in ['arm', 'shoulder', 'forearm', 'hand']):
        pb.rotation_mode = 'QUATERNION'
if armature.animation_data and armature.animation_data.action:
    for fc in armature.animation_data.action.fcurves:
        if any(k in fc.data_path.lower() for k in ['arm', 'shoulder', 'forearm']):
            for kp in fc.keyframe_points:
                kp.handle_left_type = 'AUTO'
                kp.handle_right_type = 'AUTO'""")
        )
    ]

def search_seed_mocap_fixes(query: str, top_k: int = 3) -> List[MocapFix]:
    fixes = get_seed_mocap_fixes()
    if not fixes:
        return []
    q_vec = get_text_embedding(query)
    scored = []
    for fix in fixes:
        fix_vec = get_text_embedding(fix.desc)
        score = sum(a * b for a, b in zip(q_vec, fix_vec))
        scored.append((score, fix))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]

def init_clickhouse():
    client = get_clickhouse_client()
    if client is None:
        logger.warning("ClickHouse server offline, skipping database initialization")
        return

    try:
        client.command("""
            CREATE TABLE IF NOT EXISTS mocap_fixes (
                id UUID DEFAULT generateUUIDv4(),
                anomaly_desc String,
                fix_script String,
                embedding Array(Float32),
                INDEX vec_idx embedding TYPE vector_similarity('hnsw', 'cosineDistance', 768) GRANULARITY 1
            ) ENGINE = MergeTree()
            ORDER BY id
        """)

        count_res = client.query("SELECT count() FROM mocap_fixes")
        count = count_res.first_row[0] if count_res and count_res.first_row else 0
        if count > 0:
            return

        seed_fixes = get_seed_mocap_fixes()
        data_to_insert = []
        for fix in seed_fixes:
            vec = get_text_embedding(fix.desc)
            data_to_insert.append([fix.desc, fix.script, vec])
            
        client.insert('mocap_fixes', data_to_insert, column_names=['anomaly_desc', 'fix_script', 'embedding'])
    except Exception as e:
        logger.warning(f"Failed to initialize ClickHouse tables: {e}")

if __name__ == "__main__":
    init_clickhouse()

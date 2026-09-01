import clickhouse_connect
import logging
from dataclasses import dataclass
from config import get_clickhouse_client, get_text_embedding, BLENDER_BOILERPLATE

logger = logging.getLogger(__name__)

@dataclass
class MocapFix:
    desc: str
    script: str

def init_clickhouse():
    client = get_clickhouse_client()
    
    client.command("""
        CREATE TABLE IF NOT EXISTS mocap_fixes (
            id UUID DEFAULT generateUUIDv4(),
            anomaly_desc String,
            fix_script String,
            embedding Array(Float32),
            INDEX vec_idx embedding TYPE vector_similarity('cosine', 'f32') GRANULARITY 1
        ) ENGINE = MergeTree()
        ORDER BY id
    """)
    
    count = client.query("SELECT count() FROM mocap_fixes").first_row[0]
    if count > 0:
        return

    mock_fixes = [
        MocapFix(
            desc="Jittery right arm motion during the walk cycle.",
            script=BLENDER_BOILERPLATE.format(fix_logic="for fcurve in armature.animation_data.action.fcurves:\n    if 'pose.bones[\"RightArm\"]' in fcurve.data_path:\n        for kp in fcurve.keyframe_points:\n            kp.co[1] = round(kp.co[1], 2)")
        ),
        MocapFix(
            desc="Foot sliding when character stops moving.",
            script=BLENDER_BOILERPLATE.format(fix_logic="for pb in armature.pose.bones:\n    if pb.name.startswith('Foot'):\n        pb.location = (0,0,0)")
        )
    ]
    
    try:
        data_to_insert = []
        for fix in mock_fixes:
            vec = get_text_embedding(fix.desc)
            data_to_insert.append([fix.desc, fix.script, vec])
            
        client.insert('mocap_fixes', data_to_insert, column_names=['anomaly_desc', 'fix_script', 'embedding'])
    except Exception as e:
        logger.error(f"Failed to populate mock data in ClickHouse: {e}")
        raise

if __name__ == "__main__":
    init_clickhouse()

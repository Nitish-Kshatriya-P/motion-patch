import clickhouse_connect
from vertexai.language_models import TextEmbeddingModel
from dataclasses import dataclass
from config import init_vertexai, get_clickhouse_client

@dataclass
class MocapFix:
    desc: str
    script: str

def init_clickhouse():
    init_vertexai()
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
            script="import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete()\nbpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')\narmature = bpy.context.selected_objects[0]\nbpy.ops.export_anim.bvh(filepath='/workspace/output.bvh')"
        ),
        MocapFix(
            desc="Foot sliding when character stops moving.",
            script="import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete()\nbpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')\narmature = bpy.context.selected_objects[0]\nbpy.ops.export_anim.bvh(filepath='/workspace/output.bvh')"
        )
    ]
    
    try:
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        embeddings = model.get_embeddings([f.desc for f in mock_fixes])
        
        data_to_insert = []
        for i, fix in enumerate(mock_fixes):
            data_to_insert.append([fix.desc, fix.script, embeddings[i].values])
            
        client.insert('mocap_fixes', data_to_insert, column_names=['anomaly_desc', 'fix_script', 'embedding'])
    except Exception:
        pass

if __name__ == "__main__":
    init_clickhouse()

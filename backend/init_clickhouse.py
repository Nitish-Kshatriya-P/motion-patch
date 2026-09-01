import os
import clickhouse_connect
import vertexai
from vertexai.language_models import TextEmbeddingModel

def init_clickhouse():
    print("Initializing ClickHouse Vector Database...")
    
    # Initialize Vertex AI
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)
    
    # Connect to ClickHouse
    client = clickhouse_connect.get_client(host='localhost', port=8123, username='default', password='')
    
    # Create Table for RAG
    # We use Array(Float32) for the embedding.
    client.command("""
        CREATE TABLE IF NOT EXISTS mocap_fixes (
            id UUID DEFAULT generateUUIDv4(),
            anomaly_desc String,
            fix_script String,
            embedding Array(Float32)
        ) ENGINE = MergeTree()
        ORDER BY id
    """)
    print("Table mocap_fixes created/verified.")
    
    # Check if we already have data
    count = client.query("SELECT count() FROM mocap_fixes").first_row[0]
    if count > 0:
        print(f"Table already contains {count} rows. Skipping mock data insertion.")
        return

    # Mock Historical Fixes
    mock_fixes = [
        {
            "desc": "Jittery right arm motion during the walk cycle.",
            "script": "import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete()\nbpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')\narmature = bpy.context.selected_objects[0]\n# smoothing filter on right arm\nbpy.ops.export_anim.bvh(filepath='/workspace/output.bvh')"
        },
        {
            "desc": "Foot sliding when character stops moving.",
            "script": "import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete()\nbpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')\narmature = bpy.context.selected_objects[0]\n# apply IK foot lock\nbpy.ops.export_anim.bvh(filepath='/workspace/output.bvh')"
        }
    ]
    
    try:
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        embeddings = model.get_embeddings([f["desc"] for f in mock_fixes])
        
        data_to_insert = []
        for i, fix in enumerate(mock_fixes):
            data_to_insert.append([fix["desc"], fix["script"], embeddings[i].values])
            
        client.insert('mocap_fixes', data_to_insert, column_names=['anomaly_desc', 'fix_script', 'embedding'])
        print(f"Successfully inserted {len(data_to_insert)} mock fixes into ClickHouse.")
    except Exception as e:
        print(f"Warning: Could not generate embeddings or insert data (possibly Vertex AI is mocked or not configured): {e}")

if __name__ == "__main__":
    init_clickhouse()

import os
import vertexai
import clickhouse_connect
from vertexai.language_models import TextEmbeddingModel

def get_clickhouse_client():
    import os
    return clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'), 
        port=8123, 
        username='default', 
        password='',
        settings={'allow_experimental_vector_similarity_index': 1}
    )

def init_vertexai():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)

def get_text_embedding(text: str) -> list:
    init_vertexai()
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    return model.get_embeddings([text])[0].values

BLENDER_BOILERPLATE = """import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')
armature = bpy.context.selected_objects[0]
{fix_logic}
bpy.ops.export_anim.bvh(filepath='/workspace/output.bvh')"""

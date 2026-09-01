import os
import vertexai
import clickhouse_connect

def get_clickhouse_client():
    return clickhouse_connect.get_client(host='localhost', port=8123, username='default', password='')

def init_vertexai():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)

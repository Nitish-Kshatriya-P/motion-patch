import pytest
from fastapi.testclient import TestClient
from main import app, UPLOAD_DIR
import os
import uuid
import shutil

client = TestClient(app)

@pytest.fixture(autouse=True)
def run_around_tests():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    yield
    # Cleanup after tests
    for f in os.listdir(UPLOAD_DIR):
        os.remove(os.path.join(UPLOAD_DIR, f))

def test_upload_valid_bvh():
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    response = client.post("/upload", files=files)
    assert response.status_code == 200
    assert "id" in response.json()

def test_upload_invalid_extension():
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post("/upload", files=files)
    assert response.status_code == 400

def test_upload_invalid_content():
    content = b"INVALID CONTENT"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    response = client.post("/upload", files=files)
    assert response.status_code == 400

def test_get_bvh():
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test2.bvh", content, "application/octet-stream")}
    res = client.post("/upload", files=files)
    file_id = res.json()["id"]
    
    response = client.get(f"/bvh/{file_id}")
    assert response.status_code == 200
    assert response.content == content

def test_get_nonexistent_bvh():
    response = client.get("/bvh/invalid-id")
    assert response.status_code == 404

from unittest.mock import patch, MagicMock

@patch("main.genai.Client")
def test_generate_code_success(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = "```python\nimport bpy\nprint('hello')\n```"
    mock_client.models.generate_content.return_value = mock_response
    
    response = client.post("/generate_code", json={"prompt": "make it say hello"})
    
    assert response.status_code == 200
    data = response.json()
    assert "script_id" in data
    
    script_path = os.path.join(UPLOAD_DIR, f"script_{data['script_id']}.py")
    assert os.path.exists(script_path)
    with open(script_path, "r") as f:
        content = f.read()
    assert content == "import bpy\nprint('hello')"

@patch("main.genai.Client")
def test_generate_code_error(mock_client_class):
    mock_client_class.side_effect = Exception("Vertex AI Error")
    
    response = client.post("/generate_code", json={"prompt": "make it say hello"})
    
    assert response.status_code == 500
    assert "Agent code generation failed" in response.json()["detail"]

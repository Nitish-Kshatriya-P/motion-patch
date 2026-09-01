import pytest
from fastapi.testclient import TestClient
from main import app, UPLOAD_DIR
import os
import shutil
from unittest.mock import patch, MagicMock

client = TestClient(app)

@pytest.fixture(autouse=True)
def run_around_tests():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    yield
    for f in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, f)
        if os.path.isfile(file_path):
            os.remove(file_path)
        else:
            shutil.rmtree(file_path, ignore_errors=True)

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

@patch("agent.GenerativeModel")
def test_generate_code_success(mock_model_class):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    res = client.post("/upload", files=files)
    file_id = res.json()["id"]

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model
    
    mock_response = MagicMock()
    mock_response.text = "```python\nimport bpy\nprint('hello')\n```"
    mock_model.generate_content.return_value = mock_response
    
    response = client.post("/generate_code", json={"prompt": "make it say hello", "bvh_id": file_id})
    
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert data["code"] == "import bpy\nprint('hello')"

@patch("agent.GenerativeModel")
def test_generate_code_error(mock_model_class):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    res = client.post("/upload", files=files)
    file_id = res.json()["id"]

    mock_model_class.side_effect = Exception("Vertex AI Error")
    
    with patch("main.generate_blender_script") as mock_gen:
        mock_gen.side_effect = Exception("Vertex AI Error")
        response = client.post("/generate_code", json={"prompt": "make it say hello", "bvh_id": file_id})
        
        assert response.status_code == 500
        assert "Agent code generation failed" in response.json()["detail"]

@patch("main.execute_blender_script")
def test_run_blender_success(mock_execute):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    res = client.post("/upload", files=files)
    file_id = res.json()["id"]

    def side_effect(input_bvh, script_code, upload_dir, temp_id):
        final_path = os.path.join(upload_dir, f"{temp_id}.bvh")
        with open(final_path, "w") as f:
            f.write("OUTPUT")
        return final_path
    mock_execute.side_effect = side_effect

    response = client.post("/run_blender", json={"bvh_id": file_id, "script_code": "import bpy\nprint('test')"})
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    
def test_run_blender_syntax_error():
    response = client.post("/run_blender", json={"bvh_id": "dummy", "script_code": "def bad_syntax("})
    assert response.status_code == 400
    assert "Invalid Python code syntax" in response.json()["detail"]

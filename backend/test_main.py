import pytest
from fastapi.testclient import TestClient
from main import app, UPLOAD_DIR
import os
import shutil
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def run_around_tests(client):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    yield
    for f in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, f)
        if os.path.isfile(file_path):
            os.remove(file_path)
        else:
            shutil.rmtree(file_path, ignore_errors=True)

@pytest.fixture
def test_bvh_id(client):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    response = client.post("/upload", files=files)
    return response.json()["id"]

def test_upload_valid_bvh(client):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    response = client.post("/upload", files=files)
    assert response.status_code == 200
    assert "id" in response.json()

def test_upload_invalid_extension(client):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post("/upload", files=files)
    assert response.status_code == 400

def test_upload_invalid_content(client):
    content = b"INVALID CONTENT"
    files = {"file": ("test.bvh", content, "application/octet-stream")}
    response = client.post("/upload", files=files)
    assert response.status_code == 400

def test_get_bvh(client, test_bvh_id):
    content = b"HIERARCHY\nROOT Hips\n{\n}"
    response = client.get(f"/bvh/{test_bvh_id}")
    assert response.status_code == 200
    assert response.content == content

def test_get_nonexistent_bvh(client):
    response = client.get("/bvh/invalid-id")
    assert response.status_code == 404

@pytest.fixture
def mock_chat():
    with patch("agent.GenerativeModel") as mock_model_class:
        chat = AsyncMock()
        mock_model_class.return_value.start_chat.return_value = chat
        
        mock_resp = MagicMock()
        mock_resp.text = "PASS"
        mock_model_class.return_value.generate_content_async = AsyncMock(return_value=mock_resp)
        
        yield chat

def test_generate_code_success(mock_chat, client, test_bvh_id):
    mock_response = AsyncMock()
    mock_response.text = "```python\nimport bpy\nprint('hello')\n```"
    mock_chat.send_message_async.return_value = mock_response

    response = client.post("/generate_code", data={"prompt": "make it say hello", "bvh_id": test_bvh_id}, files={"audio": ("", b"")})
    
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert data["code"] == "import bpy\nprint('hello')"

def test_generate_code_error(mock_chat, client, test_bvh_id):
    with patch("main.generate_blender_script") as mock_gen:
        mock_gen.side_effect = Exception("Vertex AI Error")
        response = client.post("/generate_code", data={"prompt": "make it say hello", "bvh_id": test_bvh_id}, files={"audio": ("", b"")})
        
        assert response.status_code == 500
        assert "Agent code generation failed" in response.json()["detail"]

def test_generate_code_empty_input(client, test_bvh_id):
    response = client.post("/generate_code", data={"prompt": "", "bvh_id": test_bvh_id})
    assert response.status_code == 400
    assert "Must provide either a prompt or audio" in response.json()["detail"]

def test_generate_code_mp3_audio(mock_chat, client, test_bvh_id):
    mock_response = AsyncMock()
    mock_response.text = "```python\nimport bpy\nprint('mp3 code')\n```"
    mock_chat.send_message_async.return_value = mock_response

    response = client.post("/generate_code", data={"bvh_id": test_bvh_id}, files={"audio": ("test.mp3", b"mp3_data", "audio/mp3")})
    assert response.status_code == 200
    assert response.json()["code"] == "import bpy\nprint('mp3 code')"

@patch("main.execute_blender_script")
def test_run_blender_success(mock_execute, client, test_bvh_id):
    def side_effect(input_bvh, script_code, upload_dir, temp_id):
        final_path = os.path.join(upload_dir, f"{temp_id}.bvh")
        with open(final_path, "w") as f:
            f.write("OUTPUT")
        return final_path
    mock_execute.side_effect = side_effect

    response = client.post("/run_blender", json={"bvh_id": test_bvh_id, "script_code": "import bpy\nprint('test')"})
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    


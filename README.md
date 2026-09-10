# MotionPatch: AI Motion Capture Studio

Detect and repair kinematic motion capture defects (foot sliding, rotation jitter, root velocity jumps, gimbal lock) in BVH files with AI agent rosters and deterministic solvers.

## Prerequisites

- **Python**: 3.10 or later
- **Node.js**: 18 or later and npm
- **Git**
- *(Optional)* **Docker Desktop**: For headless Blender repairs and ClickHouse RAG.
- *(Optional)* **Google Cloud CLI (`gcloud`)**: For live Vertex AI / Gemini agent synthesis. The system runs offline with deterministic solvers if GCP is not configured.

---

## 1. Clone Repository

```bash
git clone https://github.com/Nitish-Kshatriya-P/motion-patch.git
cd motion-patch
```

---

## 2. Backend Setup

1. Navigate to `backend` and create a virtual environment:

```bash
cd backend
python -m venv venv
```

2. Activate the virtual environment:
   - **Linux / macOS**:
     ```bash
     source venv/bin/activate
     ```
   - **Windows (PowerShell)**:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - **Windows (CMD)**:
     ```cmd
     venv\Scripts\activate.bat
     ```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 3. Environment & Google Cloud Setup

The backend uses Gemini on Vertex AI for agent roster synthesis, with automatic fallback to deterministic solvers if credentials are not provided.

### Option A: Setup Wizard (Recommended for GCP)

From the project root:

```bash
bash tools/gcp_demo_wizard.sh
```

### Option B: Manual GCP Authentication

```bash
gcloud auth application-default login
```

Set environment variables:

- **Linux / macOS**:
  ```bash
  export GOOGLE_CLOUD_PROJECT="your-project-id"
  export GOOGLE_CLOUD_LOCATION="us-central1"
  export GOOGLE_GENAI_USE_VERTEXAI="true"
  ```
- **Windows (PowerShell)**:
  ```powershell
  $env:GOOGLE_CLOUD_PROJECT="your-project-id"
  $env:GOOGLE_CLOUD_LOCATION="us-central1"
  $env:GOOGLE_GENAI_USE_VERTEXAI="true"
  ```
- **Windows (CMD)**:
  ```cmd
  set GOOGLE_CLOUD_PROJECT=your-project-id
  set GOOGLE_CLOUD_LOCATION=us-central1
  set GOOGLE_GENAI_USE_VERTEXAI=true
  ```

*(To run offline or in automated test mode without GCP, set `TESTING=1`)*

---

## 4. Optional Services

### Headless Blender (Docker)
Required only if executing Blender-based script repairs:

```bash
# From repository root:
docker build -t headless-blender -f backend/Dockerfile.blender backend

# Or from backend directory:
cd backend
docker build -t headless-blender -f Dockerfile.blender .
```

### ClickHouse RAG (Docker)
Required only if using persistent vector search for repair scripts:

```bash
docker compose up -d clickhouse
```

---

## 5. Run the Application

### Start Backend Server
From the `backend` directory (with virtual environment activated):

```bash
uvicorn main:app --reload --port 8000
```

- API Server: `http://localhost:8000`
- Interactive API Docs (Swagger): `http://localhost:8000/docs`

### Start Frontend Client
Open a second terminal, navigate to `frontend`:

```bash
cd frontend
npm install
npm run dev
```

- Web Studio: `http://localhost:5173`

---

## 6. Run Tests

### Backend Tests
From the `backend` directory:

```bash
pytest tests
```

### Frontend Tests & Lint
From the `frontend` directory:

```bash
npm run test
npm run lint
```

# Motion capture studio

This project checks motion capture files in BVH format for quality defects like foot sliding, marker dropouts, and gimbal lock flips. It synthesizes repair plans with Google Cloud Vertex AI, renders interactive 3D motion comparisons in the browser, and exports repaired BVH files through deterministic mathematical solvers or headless Blender running in Docker.

## Prerequisites

Before starting, install the following tools:

- Git
- Python 3.10 or later
- Node.js 18 or later and npm
- Docker Desktop, running locally
- Google Cloud CLI (`gcloud`) with access to a Google Cloud project with Vertex AI enabled

## Clone the repository

Clone the repository and move into the project directory:

```bash
git clone https://github.com/your-org/G-Hack.git
cd G-Hack
```

## Google Cloud setup

The backend calls Gemini models on Google Cloud Vertex AI using Application Default Credentials (ADC).

If you want an interactive setup script that links billing, verifies APIs, and exports environment values, run the setup wizard from the repository root:

```bash
bash tools/gcp_demo_wizard.sh
```

To configure credentials manually, log in with `gcloud`:

```bash
gcloud auth application-default login
```

Set the required environment variables:

- `GOOGLE_CLOUD_PROJECT`: Your Google Cloud project ID
- `GOOGLE_CLOUD_LOCATION`: The Vertex AI region, such as `us-central1`
- `GOOGLE_GENAI_USE_VERTEXAI`: Set to `true`

On Linux or macOS:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
export GOOGLE_GENAI_USE_VERTEXAI="true"
```

On Windows Command Prompt:

```cmd
set GOOGLE_CLOUD_PROJECT=your-project-id
set GOOGLE_CLOUD_LOCATION=us-central1
set GOOGLE_GENAI_USE_VERTEXAI=true
```

On Windows PowerShell:

```powershell
$env:GOOGLE_CLOUD_PROJECT="your-project-id"
$env:GOOGLE_CLOUD_LOCATION="us-central1"
$env:GOOGLE_GENAI_USE_VERTEXAI="true"
```

## Backend setup

Navigate to the `backend` folder and create a Python virtual environment:

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

On Linux or macOS:

```bash
source venv/bin/activate
```

On Windows:

```cmd
venv\Scripts\activate
```

Install the backend dependencies:

```bash
pip install fastapi uvicorn pydantic pydantic-settings google-genai google-cloud-aiplatform clickhouse-connect pytest
```

## Headless Blender container

Build the Docker image used for headless Blender script execution:

```bash
docker build -t headless-blender -f Dockerfile.blender .
```

Keep Docker Desktop running so the backend can launch this container during repair jobs.

## Start the backend server

Start FastAPI with uvicorn:

```bash
uvicorn main:app --reload --port 8000
```

The API service runs at `http://localhost:8000`. You can test endpoints and review the schema at `http://localhost:8000/docs`.

## Start the frontend application

Open a new terminal window, navigate to the `frontend` directory, install packages, and start the development server:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser to view the studio interface, upload BVH files, and inspect motion trajectories.

## Run automated tests

Run the backend test suite:

```bash
cd backend
pytest tests
```

Run frontend tests and lint checks:

```bash
cd frontend
npm run test
npm run lint
```

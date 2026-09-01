# Agentic Cinema - Single-Agent Headless Blender (Ticket 02)

This project integrates a single Agent Development Kit (ADK) agent with a headless Blender execution environment inside Docker.

## Google Cloud Vertex AI Setup

The backend has been migrated to use Google Cloud Vertex AI via Application Default Credentials (ADC) instead of a plain Gemini API key.

### Authentication

You must authenticate locally with your Google Cloud account before running the application:

```bash
gcloud auth application-default login
```

### Configuration (Environment Variables)

Configure the application by setting the following environment variables (or putting them in a `.env` file in the `backend/` directory if you use python-dotenv, though currently they should be exported to the environment):

- `GOOGLE_CLOUD_PROJECT`: Your Google Cloud Project ID.
- `GOOGLE_CLOUD_LOCATION`: The location/region to use (e.g., `us-central1`).
- `GOOGLE_GENAI_USE_VERTEXAI`: Set to `true` (default is true, but explicit is better) to use Vertex AI.

Example for Windows Command Prompt:
```cmd
set GOOGLE_CLOUD_PROJECT=your-project-id
set GOOGLE_CLOUD_LOCATION=us-central1
set GOOGLE_GENAI_USE_VERTEXAI=true
```

## Running the Backend

Ensure you have Docker running (Docker Desktop on Windows).

1. Build the headless blender Docker image (only needed once):
   ```bash
   cd backend
   docker build -t headless-blender -f Dockerfile.blender .
   ```
2. Start the FastAPI backend:
   ```bash
   cd backend
   venv\Scripts\uvicorn main:app --reload
   ```

## Running the Frontend

1. Open a new terminal.
2. Install dependencies (if not already done) and start Vite:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Running Tests

To run the backend tests (which do not require valid Google Cloud credentials thanks to mocking):
```bash
cd backend
venv\Scripts\pytest test_main.py
```

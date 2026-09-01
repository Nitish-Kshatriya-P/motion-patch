# ADR 0005: React Web Dashboard for UX

## Status
Proposed

## Context
The project must run on web, Android, or iOS. We need a versatile UI that allows animators to upload mocap files, define regions of interest, and review the agent's corrections without needing a local installation of Blender.

## Decision
We will build a **React Web Dashboard**.
- **Frontend:** React SPA (Single Page Application) hosted on **Firebase Hosting**. It features a 3D WebGL viewer (`@react-three/fiber`) to preview `.bvh` files. We are adding two extreme UX optimizations:
  1. **Multimodal Audio:** A "Hold to Speak" button allows animators to submit raw spoken feedback. The raw audio is sent directly to Gemini 1.5 Pro.
  2. **White-Box Code Editor:** Before execution, the generated `bpy` Python script is exposed in a UI code editor. Users can manually tweak parameters (e.g., smoothing strength) and re-run the code locally. This empowers the human-in-the-loop and bypasses the LLM to aggressively protect our $300 API token budget.
- **Backend:** A Python API (FastAPI) that hosts the **Google ADK** orchestration loop and executes scripts via headless Blender. Containerized and hosted on **Google Cloud Run**.

## Consequences
- **Pros:** Highly versatile, fulfills hackathon rules perfectly, and is extremely impressive to demo on video.
- **Cons:** Requires building a frontend viewer for BVH files, which can be tricky but is manageable with existing Three.js loaders.

# 01: Hello World Mocap Viewer (End-to-End Core)

**What to build:** A basic React dashboard that allows a user to upload a `.bvh` file. The file is sent to a FastAPI backend which simply stores it and returns an ID. The frontend then fetches and renders the 3D file in the browser using `@react-three/fiber` so the user can visually verify the upload. This establishes the full round-trip connection without any AI yet.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] FastAPI endpoint to receive and store a `.bvh` file
- [ ] React SPA skeleton (Vite/Next.js) with upload form
- [ ] `@react-three/fiber` viewer component capable of playing the `.bvh` animation

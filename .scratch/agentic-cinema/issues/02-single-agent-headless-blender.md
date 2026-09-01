# 02: Single-Agent Headless Blender Execution (The Baseline)

**What to build:** Introduce Google ADK and Blender. The user types a text prompt on the frontend. The FastAPI backend sends the prompt and BVH to a single ADK agent (Gemini 1.5 Pro). The agent generates a `bpy` script to apply the requested fix. The backend executes the script via a headless Blender instance to modify the `.bvh` file, and sends the fixed file back to the React viewer.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Configure Google ADK with a basic single agent prompt
- [ ] Headless Blender Python execution environment integrated into FastAPI
- [ ] UI updated to include a text prompt input field
- [ ] E2E: User types "smooth left arm", agent writes code, Blender executes, viewer updates

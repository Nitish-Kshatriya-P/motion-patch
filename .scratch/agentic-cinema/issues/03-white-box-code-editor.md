# 03: White-Box Code Editor (Human-in-the-Loop)

**What to build:** Interrupt the automated flow to protect the budget. After the agent generates the `bpy` script, the backend sends the raw code to the frontend instead of immediately executing it. The UI displays the code in an editable panel. The animator can manually tweak a variable (e.g., smoothing strength), then click "Execute" to run the final script on the backend.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Add a code editor component (e.g., Monaco) to the React frontend
- [ ] Backend logic to pause execution and yield script to client
- [ ] Backend endpoint to receive explicitly modified `bpy` script and run it via Blender

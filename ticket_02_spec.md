Ticket 02: Single-Agent Headless Blender Execution.

Introduce Google ADK and Blender. The user types a text prompt on the frontend. The FastAPI backend sends the prompt and BVH to a single ADK agent (Gemini 2.5 Pro). The agent generates a `bpy` (Blender Python) script. The backend executes the script via a headless Blender instance to modify the `.bvh` file, and sends the fixed file back to the React viewer.

Requirements:
- Configure Google ADK with a single agent prompt.
- Integrate a headless Blender Python execution environment into the FastAPI backend.
- Update the React UI to include a text prompt input field.
- Connect the end-to-end flow: User prompt -> Agent code generation -> Headless Blender execution -> UI viewer update.

Quality Guidelines:
- Sandbox the headless Blender execution to prevent arbitrary code execution vulnerabilities.
- Craft a strict system prompt for the Gemini agent to ensure the generated `bpy` script is syntactically correct and accurately modifies the BVH.

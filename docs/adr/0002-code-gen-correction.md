# ADR 0002: Code-Generation for Mocap Correction

## Status
Proposed

## Context
The agent must be versatile enough to judge the best approach to fix broken mocap data, while keeping the human in the loop.

## Decision
The agent will act as an **Agentic Technical Director (TD)**. 
Instead of trying to predict and output raw floating-point 3D coordinates (which LLMs are bad at), the agent will **write and execute Blender Python (`bpy`) scripts**.
- When an error is identified, the agent writes a specific script (e.g., applying a Butterworth filter to a jittery arm, or baking an Inverse Kinematics constraint to pin a sliding foot).
- The script is executed in a headless Blender instance to modify the data.
- The human animator can read the script, tweak the parameters (e.g., "make the filter stronger"), and accept the final output.

## Consequences
- **Pros:** Highly versatile. Code is deterministic. Animators understand scripts and parameters, fulfilling the "animator final control" requirement perfectly.
- **Cons:** Requires the agent to be highly proficient in the `bpy` API. We will need to prompt it with good `bpy` examples via RAG or context caching.

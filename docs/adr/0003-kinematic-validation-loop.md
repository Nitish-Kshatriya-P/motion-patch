# ADR 0003: Kinematic Self-Validation Loop

## Status
Proposed

## Context
The agent needs to check its own work to ensure the generated fix (e.g., removing a foot slide) is natural and doesn't introduce new anomalies (like violating joint limits). Re-rendering video for the LLM to watch every single attempt is too slow and expensive.

## Decision
We will implement a **Deterministic Validation Layer**.
1. After the agent writes and executes the `bpy` script, a secondary Python script runs "Hard Checks" against the modified mocap data.
2. These Hard Checks include:
   - Joint limits (e.g., knee cannot bend backwards).
   - Contact sliding constraints (e.g., if foot is planted, XYZ translation delta must be < 0.01 per frame).
   - Global motion continuity (no massive velocity spikes).
3. **Agentic Retry:** If a Hard Check fails, the validation script returns the specific error (e.g., "Fix failed: Left knee rotated 180 degrees at frame 45") back to the Agent. The Agent uses this context to rewrite the script and try again, up to a maximum number of retries.

## Consequences
- **Pros:** Guarantees physical accuracy. Keeps LLM token costs low by using math to verify rather than video processing.
- **Cons:** We have to manually write the Hard Check validation logic for various human joints.

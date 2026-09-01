# Domain Glossary

**MotionPatch**
A hackathon project for "Agentic Cinema: The Blockbuster Hackathon". Software that automatically detects and corrects errors in motion-capture performances, keeping the animator in the loop.

**Mocap Data**
The raw or solved skeletal animation data (format TBD, e.g., BVH, FBX).

**Problem / Error (Mocap)**
Anomalies in the motion capture data (e.g., foot sliding, jitter, intersection, occlusion). Detection methodology TBD.

**Correction (Agentic)**
The automated process of fixing the detected mocap errors while preserving the actor's original performance intent.

**Human-in-the-Loop (HITL) Validation**
The final step where an animator reviews, tweaks, or accepts the agent's corrections.

**Heuristic Flagging (Pass 1)**
A fast, non-AI programmatic scan of mocap data to find mathematical anomalies (e.g., high bone velocity) to trigger the AI agent, saving cloud costs.

**Agentic TD (Pass 2)**
The LLM acting as a Technical Director. It watches flagged video clips and writes `bpy` (Blender Python) scripts to surgically fix the animation.

**bpy**
The Blender Python API, used as the execution sandbox for our agent to manipulate 3D data deterministically.

**Hard Checks**
Deterministic mathematical constraints (e.g., joint limits, foot sliding velocity) run by a Python script after an agent's fix. If a check fails, the agent is forced to retry.

**ADK (Agent Development Kit)**
The official Google Cloud `google-cloud-aiplatform[agent_engines,adk]` Python library. Required by the hackathon rules to orchestrate the agent, replacing banned frameworks like LangChain.

**Grafana Cloud MCP Server**
The partner integration used to monitor the agent's token usage, latency, and retry loops to ensure we don't blow through the $300 budget.

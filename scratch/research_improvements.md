# Mocap Cleanup: Multi-Agent Architecture Upgrades

## 1. Multi-Agent Collaboration via Google Cloud ADK
To transition from a monolithic mocap cleanup agent to a multi-agent system, we will use the **Google Cloud Agent Development Kit (ADK)** to implement an Orchestrator-Worker model. This maximizes hackathon points for multi-agent collaboration:
*   **Supervisor/Orchestrator Agent**: Acts as the brain. It analyzes incoming BVH/FBX data, assesses the cleanup complexity, and routes specific frame ranges to specialized worker agents.
*   **Kinematics Expert Agent**: Focuses strictly on fixing joint limits, unnatural rotations, and high-frequency jitter.
*   **Contact/Foot-Skating Agent**: Specialized in resolving ground contacts, foot sliding, and weight distribution using IK constraints.
*   **QA/Judge Agent**: Validates the output from worker agents against standard animation principles (e.g., arc tracking, momentum). If anomalies remain, it triggers a feedback loop, sending the data back for refinement.

## 2. RAG on Past Fixes with ClickHouse (Partner Track)
To fulfill partner track requirements and improve accuracy, we will integrate **ClickHouse** for Vector Search and RAG:
*   **Knowledge Base**: Store metadata of past mocap fixes (e.g., pairs of messy animation curves, applied filters, and descriptions of the anomalies) in ClickHouse.
*   **Embedding Pipeline**: Use Gemini's embedding APIs to embed the semantic descriptions and kinematic signatures of motion anomalies.
*   **RAG Workflow**: When an agent encounters a difficult anomaly, it queries ClickHouse to find semantically similar past fixes. ClickHouse returns the historical correction parameters, allowing the agent to apply proven solutions rather than generating fixes from scratch.

## 3. Production-Ready Architecture (Gemini Enterprise)
To score high on the "production-ready architecture" criteria using the **Gemini Enterprise Agent Platform**:
*   **Batch Processing & Scalability**: Mocap cleanup is compute-intensive. We will use Vertex AI Agent Engine and Cloud Run to containerize agents, allowing asynchronous batch processing of large animation sequences in parallel.
*   **Model Context Protocol (MCP)**: Expose our 3D DCC tools (Maya/Blender Python APIs) to the agents using MCP. This standardizes tool use and enforces security boundaries.
*   **Observability & Guardrails**: Utilize ADK's native integrations to log agent-to-agent (A2A) communications and tool calls into BigQuery for debugging and audit trails, ensuring zero-trust execution.

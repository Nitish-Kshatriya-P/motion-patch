# ADR 0004: Orchestration and Partner Track

## Status
Proposed

## Context
The "Agentic Cinema" hackathon rules dictate strict constraints on orchestration frameworks and mandate the use of a Partner Track at runtime. We cannot use LangChain, CrewAI, or non-Google LLMs.

## Decision
1. **Orchestration:** We will build a **Dynamic Multi-Agent System** natively using the **Google Cloud Agent Development Kit (ADK)** (`google-cloud-aiplatform[agent_engines,adk]`). Instead of a monolithic retry loop, we will spin up specialized agents (e.g., Kinematics Expert, Contact Expert, QA Judge) dynamically based on the complexity of the task.
2. **Partner Track:** We will enter the **ClickHouse Track**. 
   - We will integrate **ClickHouse** into our ADK loop as a RAG (Retrieval-Augmented Generation) memory bank. The dynamic agents will use ClickHouse MCP to query historical fixes before attempting to write scripts. This ensures we strictly meet the hackathon's "runtime use" requirement and vastly improves the quality of our output.

## Consequences
- **Pros:** 100% compliant with hackathon rules. Solves the visibility problem of autonomous agents.
- **Cons:** Requires setting up Grafana Cloud and instrumenting the ADK.

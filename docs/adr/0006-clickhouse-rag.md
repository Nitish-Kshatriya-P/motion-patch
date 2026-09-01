# ADR 0006: ClickHouse RAG for Historical Fixes

## Status
Proposed

## Context
1. We must select a primary partner track for the hackathon judging.
2. Generating kinematic `bpy` scripts from scratch every time is prone to hallucinations and is token-expensive.
3. We need a way for the dynamic agent system to "learn" from past successful mocap fixes to improve quality over time.

## Decision
We will completely pivot our primary partner track to **ClickHouse**.
1. **Knowledge Base:** We will use ClickHouse as a Vector Database to store metadata and embeddings of past successful mocap fixes (e.g., pairing the semantic description of a "foot slide" with the specific filter parameters used to fix it).
2. **RAG Workflow:** When our dynamic agents encounter a complex anomaly, they will first query ClickHouse using MCP to find semantically similar past fixes. ClickHouse returns the proven parameters, allowing the agent to apply a high-quality fix rather than guessing from scratch.

## Consequences
- **Pros:** Massively increases output quality. Strongly fulfills the ClickHouse partner track requirement. Demonstrates high "Creativity & Innovation" by giving the agents long-term memory.
- **Cons:** Requires setting up ClickHouse and an embedding pipeline for motion data.

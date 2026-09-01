# Agentic Cinema: The Blockbuster Hackathon - Valid Components

This document outlines the allowed and prohibited components, partner track requirements, and permitted SDKs for the "Agentic Cinema: The Blockbuster Hackathon," based on the official hackathon rules and provided project resources.

## 1. Allowed and Prohibited Components

**Allowed Google Cloud AI Components:**
*   **Gemini** (as the core LLM/multimodal model)
*   **Google Cloud Agent Builder** (including Agent Engine)
*   **Gemini Enterprise Agent Platform**
*   **Gemini CLI** and **Gemini Code Assist** (for AI-assisted coding during development)

**Prohibited Components:**
*   No third-party AI models (e.g., **no OpenAI, Anthropic, etc.**).
*   No third-party agent orchestration frameworks (e.g., **no LangChain, no CrewAI**).
*   No external AI APIs other than those provided by Google Cloud and the selected official partner.
*   **Requirement:** You *must* orchestrate the agent natively using the designated Google Cloud ecosystem tools.

## 2. Partner Track Requirements

The hackathon features five official partner tracks. Participants must integrate a product or a **Model Context Protocol (MCP)** server from at least one of these partners:

1.  **IBM**
2.  **Grafana Labs**
3.  **Parallel**
4.  **ClickHouse**
5.  **Replit**

**Integration at Runtime:**
*   The chosen partner's service or MCP server must be integrated *at runtime* as part of your media and entertainment workflow.
*   Your codebase and demo video must demonstrate the actual runtime use of both Google Cloud and the partner's service.
*   *Project Note:* As outlined in `docs/adr/0004-orchestration-and-partner.md`, this project is targeting the **ClickHouse Track** by integrating ClickHouse as a Vector Database/RAG system to give the dynamic agents long-term memory of past successful mocap fixes.

## 3. Permitted SDKs

To remain compliant, developers must use the official Google Cloud libraries:

*   **Google Cloud AI Platform SDK:** `google-cloud-aiplatform`
*   **Agent Development Kit (ADK):** `google-cloud-aiplatform[agent_engines,adk]` (or `google-adk`). This Python library is explicitly required to orchestrate the agent and perform function calling natively, replacing banned frameworks like LangChain.

## Sources
*   Official [Agentic Cinema Devpost Rules](https://agentic-cinema.devpost.com/)
*   Project `docs/GLOSSARY.md`
*   Project `docs/adr/0004-orchestration-and-partner.md`

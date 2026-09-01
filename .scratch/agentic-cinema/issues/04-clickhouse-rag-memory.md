# 04: ClickHouse RAG Memory Bank (Partner Track)

**What to build:** Fulfill the ClickHouse partner track. Provision a ClickHouse Vector Database and populate it with a few mock historical mocap fixes (anomaly descriptions + `bpy` script pairs). Equip the ADK agent with a ClickHouse MCP tool. When the agent receives a prompt, it queries ClickHouse for similar past fixes to generate high-quality code.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Provision ClickHouse Vector DB schema
- [ ] Create ClickHouse MCP tool for ADK integration
- [ ] Agent prompt updated to enforce querying the RAG memory before code generation

# Gates: Ticket 07 ClickHouse RAG Memory Bank Runtime MCP Integration

Scope: Implement ClickHouse RAG memory bank and FastMCP integration for mocap repair agents with zero comments and deterministic fallbacks.

- [x] G1: config.py supports deterministic normalized 768-dim vector embeddings and graceful ClickHouse client timeouts
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_deterministic_embedding_properties
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ================ 1 passed, 12 deselected, 2 warnings in 4.56s =================

- [x] G2: init_clickhouse.py has expanded seed dataset across foot, jitter, root, and arm categories plus in-memory fallback
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k "test_seed_fixes or test_seed_ranking"
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ================ 2 passed, 11 deselected, 2 warnings in 5.31s =================

- [x] G3: mcp_server.py query_rag_memory returns formatted past fixes from ClickHouse or in-memory seed fallback
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_query_rag_memory
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ================= 4 passed, 9 deselected, 2 warnings in 5.30s =================

- [x] G4: agent.py incorporates RAG memory query into worker code generation
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_worker_agent_incorporates_rag_memory
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ================ 1 passed, 12 deselected, 2 warnings in 4.12s =================

- [x] G5: backend/tests/test_mcp.py runs and passes all MCP and RAG integration tests
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ======================= 22 passed, 4 warnings in 14.20s =======================

- [x] G6: Full backend pytest test suite passes completely
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ======================= 76 passed, 7 warnings in 21.50s =======================

- [x] G7: Frontend vitest test suite passes completely
  CHECK: npm --prefix frontend run test -- --run
  EXPECT: passed
  EVIDENCE: Test Files 10 passed (10) | Tests 70 passed (70)

- [x] G8: Zero comments rule verified across all touched and new files
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_zero_comments_rule
  EXPECT: passed
  EVIDENCE: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html | ================ 1 passed, 21 deselected, 2 warnings in 6.78s =================

- [x] G9: mcp_server.py exposes run_select_query, list_databases, and list_tables with read-only query guardrails
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k "test_run_select_query or test_list_databases or test_list_tables"
  EXPECT: passed
  EVIDENCE: 5 passed, 17 deselected in 5.12s

- [x] G10: agent.py provides get_clickhouse_mcp_toolset using ADK MCPToolset and Stdio/StreamableHTTP parameters
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_get_clickhouse_mcp_toolset_instantiation
  EXPECT: passed
  EVIDENCE: 1 passed, 21 deselected in 4.30s

- [x] G11: agent.py supports dynamic agent instantiation with ClickHouse MCP tools
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_instantiate_dynamic_agent_with_mcp_tools
  EXPECT: passed
  EVIDENCE: 1 passed, 21 deselected in 4.15s


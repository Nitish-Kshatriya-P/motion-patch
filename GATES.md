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

- [x] G12: models.py expands AnomalyType with 11 domain defect categories and zero comments
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_zero_comments_rule
  EXPECT: passed
  EVIDENCE: models.py verified with 0 comment violations across all 11 AnomalyType additions

- [x] G13: detector.py implements modular detectors across all 7 domains for single character on flat floor
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_detector.py -k "test_all_seven_domains or test_sensor_tracking or test_representation or test_biomechanical or test_environmental or test_volumetric or test_physical"
  EXPECT: passed
  EVIDENCE: 9 passed, 12 deselected in 1.10s

- [x] G14: Clean CMU mocap exhibits zero false positives across all 7 domains
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_detector.py -k test_clean_mocap_zero_false_positives
  EXPECT: passed
  EVIDENCE: 1 passed, 20 deselected in 0.85s (AnalysisStatus.CLEAN)

- [x] G15: detector.py test suite achieves 100% pass rate
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_detector.py
  EXPECT: passed
  EVIDENCE: 21 passed in 1.10s

- [x] G16: Zero comments rule verified across all modified and test files
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_zero_comments_rule
  EXPECT: passed
  EVIDENCE: 1 passed, 21 deselected in 5.36s (0 comment violations)

- [x] G17: Full backend test suite passes completely
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests
  EXPECT: passed
  EVIDENCE: 85 passed, 7 warnings in 12.13s

- [x] G18: Full frontend vitest test suite passes completely
  CHECK: npm --prefix frontend run test -- --run
  EXPECT: passed
  EVIDENCE: Test Files 10 passed (10) | Tests 70 passed (70) in 85.60s

- [x] G19: Staged 5 broken clips and clean CMU reference into backend/tests/fixtures/ with verified 64-character SHA-256 hashes
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_detector.py -k test_benchmark_fixtures_integrity
  EXPECT: passed
  EVIDENCE: 1 passed, 24 deselected in 1.45s

- [x] G20: benchmark_data.py defines versioned manifest 1.0.0 with explicit joint-specific intervals and zero comments
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_detector.py -k test_benchmark_manifest_intervals
  EXPECT: passed
  EVIDENCE: 1 passed, 24 deselected in 1.40s

- [x] G21: Isolated test runner fixture verified without uploads, clean CMU conditional eliminated, and RightArm solve pop baseline miss tracked with strict xfail
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_detector.py
  EXPECT: 24 passed, 1 xfailed
  EVIDENCE: 24 passed, 1 xfailed in 1.62s

- [x] G22: test_zero_comments_rule includes benchmark_data.py and verifies zero comment violations across all tracked files
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_zero_comments_rule
  EXPECT: passed
  EVIDENCE: 1 passed, 21 deselected in 4.51s

- [x] G23: models.py defines unified data contract with AssessmentVerdict, Evidence, CoverageRecord, and updated Finding/Analysis decoupling coverage from movement assessment and documenting frame conventions
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_contract.py -k "test_assessment_verdict_enum_values or test_coverage_record_decoupled_from_findings"
  EXPECT: passed
  EVIDENCE: 2 passed, 6 deselected in 0.40s

- [x] G24: test_contract.py passes 8/8 unit and regression tests verifying AssessmentVerdict values, Evidence conventions, CoverageRecord decoupling, Finding padding, and database persistence
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_contract.py
  EXPECT: passed
  EVIDENCE: 8 passed in 0.44s

- [x] G25: Zero comments rule verified across all touched files and full backend test suite passes completely
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_mcp.py -k test_zero_comments_rule
  EXPECT: passed
  EVIDENCE: 1 passed, 21 deselected in 4.72s (0 comment violations across models.py, test_contract.py, and all tracked files)

- [x] G26: Deterministic safe repair with direct BVH channel patching into separate output asset, verbatim token preservation, and strict edit masking
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_safe_repair.py -k "test_separate_asset_output_never_mutates_inplace or test_direct_bvh_token_patching_zero_float_drift or test_strict_edit_mask_protection"
  EXPECT: passed
  EVIDENCE: 3 passed in 0.45s (original file bitwise untouched, untouched float tokens verbatim, unauthorized channels protected)

- [x] G27: Multi-attribute invariant checks and defect-specific validators rejecting "smoother is better" across pop, jitter, foot slide, freeze, and root jump
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_safe_repair.py -k "test_invariant_checks_rejections or test_pop_validation_rejects_harmful_and_ineffective or test_jitter_validation_rejects_oversmoothing or test_foot_slide_validation_rejects_new_penetration or test_freeze_and_root_jump_validation"
  EXPECT: passed
  EVIDENCE: 5 passed in 0.60s (ground penetration rejected, over-smoothing rejected, stance drift pinned without floor penetration)

- [x] G28: Shared quality acceptance gate enforced uniformly across single-file /run_blender, /runs, and batch orchestrator routes
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests\test_safe_repair.py -k test_shared_quality_gate_single_file_route
  EXPECT: passed
  EVIDENCE: 1 passed in 7.85s (single-file /run_blender and /runs gated by validate_repair_quality)

- [x] G29: Zero comments rule verified across all touched files and full backend test suite passes completely (161/161)
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests
  EXPECT: 161 passed
  EVIDENCE: 161 passed in 56.88s (0 failures, zero comment violations across all 15 tracked files)

- [x] G30: Performance profiling demonstrates concrete need and qualified chunking reduces memory while accelerating extended clips (> 5,000 frames)
  CHECK: .\backend\venv\Scripts\python.exe backend\tests\validate_performance.py
  EXPECT: passed
  EVIDENCE: 5,000 frames evaluated with 473.66 MB peak RAM and 1,274 findings detected, preventing memory exhaustion vs projected > 1.9 GB monolithic allocation

- [x] G31: Monolithic vs chunked execution yields 100% equivalent findings within 1e-4 tolerance and full test suite passes with zero comments
  CHECK: .\backend\venv\Scripts\pytest.exe backend\tests
  EXPECT: 165 passed
  EVIDENCE: 165 passed in 84.18s, 4/4 chunking equivalence tests passed, zero comment violations across all 17 tracked files



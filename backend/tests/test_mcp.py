import os
os.environ["TESTING"] = "1"
import math
import pytest
from unittest.mock import patch, MagicMock

import agent
from config import get_text_embedding, get_clickhouse_client, generate_deterministic_embedding
from init_clickhouse import get_seed_mocap_fixes, search_seed_mocap_fixes, init_clickhouse
from mcp_server import (
    query_rag_memory,
    format_past_fixes,
    get_shared_clickhouse_client,
    run_select_query,
    list_databases,
    list_tables,
)
from agent import (
    init_mcp,
    cleanup_mcp,
    query_clickhouse_rag,
    query_rag_memory_sync,
    query_clickhouse_select,
    query_clickhouse_select_sync,
    list_clickhouse_tables,
    list_clickhouse_tables_sync,
    get_clickhouse_mcp_toolset,
    instantiate_dynamic_agent,
    generate_worker_code,
    synthesize_agent_roster,
    validate_qa_script,
)

def test_deterministic_embedding_properties():
    vec1 = get_text_embedding("planted foot sliding on floor")
    assert len(vec1) == 768
    mag = math.sqrt(sum(x * x for x in vec1))
    assert abs(mag - 1.0) < 1e-3

    vec2 = get_text_embedding("planted foot sliding on floor")
    assert vec1 == vec2

    vec_empty = get_text_embedding("")
    assert len(vec_empty) == 768
    mag_empty = math.sqrt(sum(x * x for x in vec_empty))
    assert abs(mag_empty - 1.0) < 1e-3

    vec_foot_similar = get_text_embedding("foot sliding floor contact pinning")
    vec_root = get_text_embedding("root translation velocity jump discontinuity")

    sim_foot_foot = sum(a * b for a, b in zip(vec1, vec_foot_similar))
    sim_foot_root = sum(a * b for a, b in zip(vec1, vec_root))
    assert sim_foot_foot > sim_foot_root

def test_seed_fixes_structure_and_qa_validity():
    fixes = get_seed_mocap_fixes()
    assert len(fixes) >= 4
    categories = {f.category for f in fixes}
    assert "foot_sliding" in categories
    assert "rotation_jitter" in categories
    assert "root_jump" in categories
    assert "arm_gimbal_lock" in categories

    for fix in fixes:
        assert len(fix.desc) > 0
        assert len(fix.script) > 0
        is_valid, err = validate_qa_script(fix.script)
        assert is_valid is True, f"Script for {fix.category} failed QA: {err}"

def test_seed_ranking_accuracy_for_mocap_categories():
    foot_results = search_seed_mocap_fixes("planted foot sliding and ground penetration", top_k=1)
    assert len(foot_results) == 1
    assert foot_results[0].category == "foot_sliding"

    jitter_results = search_seed_mocap_fixes("spine rotation jitter and high frequency noise", top_k=1)
    assert len(jitter_results) == 1
    assert jitter_results[0].category == "rotation_jitter"

    root_results = search_seed_mocap_fixes("root translation velocity jumps across frames", top_k=1)
    assert len(root_results) == 1
    assert root_results[0].category == "root_jump"

    arm_results = search_seed_mocap_fixes("arm shoulder gimbal lock rotational angle anomalies", top_k=1)
    assert len(arm_results) == 1
    assert arm_results[0].category == "arm_gimbal_lock"

def test_query_rag_memory_tool_direct_and_formatting():
    res_foot = query_rag_memory("planted foot sliding")
    assert "Past Fix Reference:" in res_foot
    assert "import bpy" in res_foot
    assert "foot" in res_foot.lower() or "toe" in res_foot.lower()

    res_jitter = query_rag_memory("spine rotation jitter")
    assert "Past Fix Reference:" in res_jitter
    assert "fcurves" in res_jitter

    res_root = query_rag_memory("root motion velocity jump")
    assert "Past Fix Reference:" in res_root
    assert "location" in res_root

    empty_res = format_past_fixes([])
    assert empty_res == "No past fixes found in memory bank."

def test_query_rag_memory_with_mocked_clickhouse():
    mock_client = MagicMock()
    mock_query_res = MagicMock()
    mock_query_res.result_rows = [
        ("Mocked foot fix description", "import bpy\narmature = bpy.context.selected_objects[0]\npass")
    ]
    mock_client.query.return_value = mock_query_res

    with patch("mcp_server.get_shared_clickhouse_client", return_value=mock_client):
        res = query_rag_memory("foot sliding")
        assert "Mocked foot fix description" in res
        assert mock_client.query.called

def test_query_rag_memory_falls_back_when_clickhouse_query_fails():
    mock_client = MagicMock()
    mock_client.query.side_effect = RuntimeError("ClickHouse connection dropped")

    with patch("mcp_server.get_shared_clickhouse_client", return_value=mock_client):
        res = query_rag_memory("planted foot sliding")
        assert "Past Fix Reference:" in res
        assert "import bpy" in res

def test_init_clickhouse_offline_resilience():
    with patch("init_clickhouse.get_clickhouse_client", return_value=None):
        init_clickhouse()

def test_cleanup_mcp_idempotence():
    import asyncio
    cleanup_res = cleanup_mcp()
    if asyncio.iscoroutine(cleanup_res):
        asyncio.run(cleanup_res)
    assert agent.mcp_session is None

@pytest.mark.anyio
async def test_mcp_client_lifecycle_full():
    await init_mcp()
    assert agent.mcp_session is not None
    res = await query_clickhouse_rag("planted foot sliding")
    assert "Past Fix Reference:" in res
    assert "import bpy" in res
    await cleanup_mcp()
    assert agent.mcp_session is None

@pytest.mark.anyio
async def test_query_clickhouse_rag_fallback_without_session():
    await cleanup_mcp()
    res = await query_clickhouse_rag("planted foot sliding")
    assert "Past Fix Reference:" in res
    assert "import bpy" in res

def test_query_rag_memory_sync_helper():
    res = query_rag_memory_sync("spine rotation jitter")
    assert "Past Fix Reference:" in res
    assert "import bpy" in res

def test_worker_agent_incorporates_rag_memory():
    roster = synthesize_agent_roster(prompt="Fix foot sliding on ground plane and spine jitter")
    assert len(roster) >= 1
    for spec in roster:
        code = generate_worker_code(spec, prompt="Fix foot sliding")
        assert len(code) > 0
        assert "armature" in code

def test_run_select_query_forbidden_query_types():
    assert "forbidden" in run_select_query("DROP TABLE mocap_fixes").lower()
    assert "forbidden" in run_select_query("INSERT INTO mocap_fixes VALUES (1)").lower()
    assert "forbidden" in run_select_query("ALTER TABLE mocap_fixes DELETE WHERE 1").lower()
    assert "forbidden" in run_select_query("TRUNCATE TABLE mocap_fixes").lower()

def test_run_select_query_offline_fallback():
    with patch("mcp_server.get_shared_clickhouse_client", return_value=None):
        res = run_select_query("SELECT count() FROM mocap_fixes")
        assert "ClickHouse offline" in res

def test_run_select_query_with_mocked_results():
    mock_client = MagicMock()
    mock_res = MagicMock()
    mock_res.column_names = ["category", "total"]
    mock_res.result_rows = [["foot_sliding", 10], ["rotation_jitter", 5]]
    mock_client.query.return_value = mock_res
    with patch("mcp_server.get_shared_clickhouse_client", return_value=mock_client):
        res = run_select_query("SELECT category, count() FROM mocap_fixes GROUP BY category")
        assert "category | total" in res
        assert "foot_sliding | 10" in res

def test_list_databases_offline_and_mocked():
    with patch("mcp_server.get_shared_clickhouse_client", return_value=None):
        res_offline = list_databases()
        assert "default" in res_offline

    mock_client = MagicMock()
    mock_res = MagicMock()
    mock_res.result_rows = [["default"], ["system"], ["test_db"]]
    mock_client.query.return_value = mock_res
    with patch("mcp_server.get_shared_clickhouse_client", return_value=mock_client):
        res_mocked = list_databases()
        assert "test_db" in res_mocked

def test_list_tables_offline_and_mocked():
    with patch("mcp_server.get_shared_clickhouse_client", return_value=None):
        res_offline = list_tables("default")
        assert "mocap_fixes" in res_offline

    mock_client = MagicMock()
    mock_res = MagicMock()
    mock_res.result_rows = [["mocap_fixes"], ["kinematic_logs"]]
    mock_client.query.return_value = mock_res
    with patch("mcp_server.get_shared_clickhouse_client", return_value=mock_client):
        res_mocked = list_tables("default")
        assert "kinematic_logs" in res_mocked

def test_query_clickhouse_select_sync_helper():
    res = query_clickhouse_select_sync("DROP TABLE forbidden")
    assert "forbidden" in res.lower()

def test_list_clickhouse_tables_sync_helper():
    res = list_clickhouse_tables_sync()
    assert "mocap_fixes" in res

def test_get_clickhouse_mcp_toolset_instantiation():
    toolset = get_clickhouse_mcp_toolset()
    assert toolset is not None
    assert hasattr(toolset, "tool_filter")

def test_instantiate_dynamic_agent_with_mcp_tools():
    from models import AgentSpecification
    spec = AgentSpecification(
        agent_id="test-agent",
        role="Kinematic SQL Analyst",
        assigned_joints=["LeftFoot"],
        target_bones=["LeftFoot"],
        target_frames=[0, 100],
        tools=["query_clickhouse_rag", "run_select_query", "list_tables"],
        status="SPAWNED",
    )
    inst = instantiate_dynamic_agent(spec)
    assert len(inst.tools) == 3
    assert inst.tools[0] == query_clickhouse_rag
    assert inst.tools[1] == query_clickhouse_select
    assert inst.tools[2] == list_clickhouse_tables

def test_zero_comments_rule():
    import re
    c_comment = "/" + "*"
    cpp_comment = "/" + "/"
    hash_char = chr(35)
    pattern = re.compile(rf"(?<!:){re.escape(cpp_comment)}(?!/)|(?<!:){re.escape(c_comment)}|{hash_char}(?![\da-fA-F]{{3,6}}\b)")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(project_root, "config.py"),
        os.path.join(project_root, "init_clickhouse.py"),
        os.path.join(project_root, "mcp_server.py"),
        os.path.join(project_root, "agent.py"),
        os.path.join(project_root, "tests", "test_mcp.py"),
    ]
    violations = []
    for fpath in target_files:
        with open(fpath, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, 1):
                if pattern.search(line):
                    violations.append(f"{os.path.basename(fpath)}:{idx}: {line.strip()}")
    assert len(violations) == 0, f"Comment violations detected:\n" + "\n".join(violations)

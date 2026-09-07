import sys
import logging
import re
from typing import List, Tuple
from mcp.server.fastmcp import FastMCP
from config import get_text_embedding, get_clickhouse_client
from init_clickhouse import search_seed_mocap_fixes

logger = logging.getLogger(__name__)

_client = None

def get_shared_clickhouse_client():
    global _client
    if _client is None:
        try:
            _client = get_clickhouse_client()
        except Exception:
            _client = None
    return _client

def format_past_fixes(fixes: List[Tuple[str, str]]) -> str:
    if not fixes:
        return "No past fixes found in memory bank."
    parts = []
    for desc, script in fixes:
        parts.append(
            f"Past Fix Reference:\nDescription: {desc}\nScript:\n```python\n{script}\n```"
        )
    return "\n\n".join(parts)

mcp_server = FastMCP("ClickHouse MCP Server")

@mcp_server.tool(description="Executes a read-only SQL query on the ClickHouse cluster and returns the tabular result. Only SELECT, SHOW, DESCRIBE, and EXPLAIN queries are permitted.")
def run_select_query(query: str) -> str:
    cleaned = query.strip()
    first_word = cleaned.split()[0].upper() if cleaned else ""
    allowed = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
    if first_word not in allowed:
        return f"Permission error: Query type '{first_word}' is forbidden. ClickHouse MCP server only permits read-only analytical queries."
    client = get_shared_clickhouse_client()
    if client is None:
        return "ClickHouse offline: unable to execute query without active connection."
    try:
        res = client.query(cleaned)
        if not res or not res.result_rows:
            return "Empty result set (0 rows returned)."
        col_names = res.column_names or [f"col_{i}" for i in range(len(res.result_rows[0]))]
        header = " | ".join(str(c) for c in col_names)
        sep = "-+-".join("-" * max(len(str(c)), 3) for c in col_names)
        row_lines = [" | ".join(str(val) for val in row) for row in res.result_rows[:100]]
        return f"{header}\n{sep}\n" + "\n".join(row_lines)
    except Exception as e:
        return f"ClickHouse execution error: {e}"

@mcp_server.tool(description="Lists all databases present on the ClickHouse cluster.")
def list_databases() -> str:
    client = get_shared_clickhouse_client()
    if client is None:
        return "default\nsystem"
    try:
        res = client.query("SHOW DATABASES")
        if res and res.result_rows:
            return "\n".join(str(r[0]) for r in res.result_rows)
        return "default"
    except Exception as e:
        return f"ClickHouse execution error: {e}"

@mcp_server.tool(description="Lists all tables within a specified database in ClickHouse.")
def list_tables(database: str = "default") -> str:
    client = get_shared_clickhouse_client()
    if client is None:
        return "mocap_fixes"
    try:
        clean_db = re.sub(r"[^a-zA-Z0-9_]", "", database) or "default"
        res = client.query(f"SHOW TABLES FROM {clean_db}")
        if res and res.result_rows:
            return "\n".join(str(r[0]) for r in res.result_rows)
        return f"No tables found in database '{clean_db}'."
    except Exception as e:
        return f"ClickHouse execution error: {e}"

@mcp_server.tool(description="Queries the ClickHouse RAG memory bank for similar historical anomaly fixes based on a description of the problem. You MUST use this tool to find past solutions before writing code.")
def query_rag_memory(anomaly_query: str) -> str:
    client = get_shared_clickhouse_client()
    if client is not None:
        try:
            q_vec = get_text_embedding(anomaly_query)
            res = client.query(
                "SELECT anomaly_desc, fix_script FROM mocap_fixes ORDER BY cosineDistance(embedding, {vec:Array(Float32)}) ASC LIMIT 3",
                parameters={"vec": q_vec}
            )
            if res and res.result_rows:
                return format_past_fixes([(r[0], r[1]) for r in res.result_rows])
        except Exception as e:
            logger.warning(f"ClickHouse query failed: {e}")

    seed_fixes = search_seed_mocap_fixes(anomaly_query, top_k=3)
    if seed_fixes:
        return format_past_fixes([(f.desc, f.script) for f in seed_fixes])

    return "No past fixes found in memory bank."

if __name__ == "__main__":
    mcp_server.run()

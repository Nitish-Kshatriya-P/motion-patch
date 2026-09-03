from mcp.server.fastmcp import FastMCP
from config import get_text_embedding, get_clickhouse_client
import sys

_client = None

def get_shared_clickhouse_client():
    global _client
    if _client is None:
        _client = get_clickhouse_client()
    return _client

mcp_server = FastMCP("ClickHouse RAG Memory")

@mcp_server.tool(description="Queries the ClickHouse RAG memory bank for similar historical anomaly fixes based on a description of the problem. You MUST use this tool to find past solutions before writing code.")
def query_rag_memory(anomaly_query: str) -> str:
    return "No past fixes found in memory bank."

if __name__ == "__main__":
    mcp_server.run()

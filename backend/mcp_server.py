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
    try:
        query_vector = get_text_embedding(anomaly_query)
        client = get_shared_clickhouse_client()
        
        query = """
            SELECT anomaly_desc, fix_script, cosineDistance(embedding, {query_vector:Array(Float32)}) as dist
            FROM mocap_fixes
            ORDER BY dist ASC
            LIMIT 3
        """
        result = client.query(query, parameters={'query_vector': query_vector})
        
        if not result.result_rows:
            return "No past fixes found in memory bank."
            
        fixes_text = "Past fixes found:\n\n"
        for row in result.result_rows:
            fixes_text += f"Anomaly: {row[0]}\nScript:\n```python\n{row[1]}\n```\n\n"
            
        return fixes_text
    except Exception as e:
        return f"Error querying memory bank: {e}"

if __name__ == "__main__":
    mcp_server.run()

from mcp.server.fastmcp import FastMCP
from vertexai.language_models import TextEmbeddingModel
from config import init_vertexai, get_clickhouse_client
import sys

mcp_server = FastMCP("ClickHouse RAG Memory")

@mcp_server.tool()
def query_rag_memory(anomaly_query: str) -> str:
    """Queries the ClickHouse RAG memory bank for similar historical anomaly fixes based on a description of the problem. You MUST use this tool to find past solutions before writing code."""
    try:
        init_vertexai()
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        embeddings = model.get_embeddings([anomaly_query])
        query_vector = embeddings[0].values
        
        client = get_clickhouse_client()
        
        query = f"""
            SELECT anomaly_desc, fix_script, cosineDistance(embedding, {query_vector}) as dist
            FROM mocap_fixes
            ORDER BY dist ASC
            LIMIT 3
        """
        result = client.query(query)
        
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

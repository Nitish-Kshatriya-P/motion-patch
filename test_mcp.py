import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from agent import init_mcp, cleanup_mcp, query_clickhouse_rag

async def main():
    await init_mcp()
    print("MCP initialized")
    res = await query_clickhouse_rag('speed')
    print("Result:", res)
    await cleanup_mcp()

if __name__ == '__main__':
    asyncio.run(main())

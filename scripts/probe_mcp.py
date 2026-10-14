"""Verify 1mcp connectivity without model/API calls."""
import argparse
import asyncio
import json
from pathlib import Path
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:3050/mcp')
    parser.add_argument('--call', help='Tool name to invoke; optional')
    parser.add_argument('--arguments', default='{}')
    parser.add_argument('--snapshot', help='Save complete tools/list response to JSON')
    args = parser.parse_args()
    async with streamablehttp_client(args.url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            if args.snapshot:
                Path(args.snapshot).write_text(response.model_dump_json(indent=2), encoding='utf-8')
            print(json.dumps({'tool_count':len(response.tools), 'tools':[tool.name for tool in response.tools]}, ensure_ascii=False))
            if args.call:
                result = await session.call_tool(args.call, json.loads(args.arguments))
                print(result.model_dump_json())
                if result.isError:
                    raise RuntimeError('MCP tool returned isError; inspect the output above.')

asyncio.run(main())

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# DeepWiki's public MCP server -- no auth required, reachable over plain
# HTTP (Streamable HTTP transport) instead of a spawned local process.
URL = "https://mcp.deepwiki.com/mcp"


async def main() -> None:  # async because everything below is I/O (network), not CPU work -- await lets us wait without blocking the whole program
    # async with = await ctx.__aenter__()/__aexit__() under the hood: opens the
    # connection, guarantees cleanup even on exception. (read, write, _) unpacks
    # the three things streamablehttp_client hands back; we don't need the third.
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()  # async, not synchronous -- but await does force this line to finish before list_tools() runs

            tools = await session.list_tools()
            print("Tools exposed by the remote DeepWiki server:")
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            result = await session.call_tool(
                "read_wiki_structure",
                {"repoName": "modelcontextprotocol/servers"},
            )
            print(
                "\nResult of calling `read_wiki_structure` on "
                "modelcontextprotocol/servers:"
            )
            print(result.content[0].text[:500] + "...\n")


if __name__ == "__main__":
    asyncio.run(main())

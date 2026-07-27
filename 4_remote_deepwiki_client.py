import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# DeepWiki's public MCP server -- no auth required, reachable over plain
# HTTP (Streamable HTTP transport) instead of a spawned local process.
URL = "https://mcp.deepwiki.com/mcp"


async def main() -> None: #Why do we need async here?
    async with streamablehttp_client(URL) as (read, write, _): #with keyword: safely close streamablehttp_client after the inner code? # as (read, write, _) defines the returned values
        async with ClientSession(read, write) as session:
            await session.initialize() #synchronous

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

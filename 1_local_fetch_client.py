import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Spawns the official reference "fetch" MCP server (Python, via uvx) as a
# child process and talks to it over stdio -- the standard transport for
# local MCP servers.
server_params = StdioServerParameters(
    command="uvx",  # uv installs deps into *our* project; uvx runs someone else's package in a throwaway env instead
    args=["mcp-server-fetch"],
)


async def main() -> None:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools exposed by the local fetch server:")
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            result = await session.call_tool(
                "fetch", {"url": "https://google.com"}
            )
            print("\nResult of calling `fetch` on https://modelcontextprotocol.io:")
            print(result.content[0].text[:500] + "...\n")


if __name__ == "__main__":
    asyncio.run(main())

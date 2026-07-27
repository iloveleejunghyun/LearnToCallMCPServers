import asyncio

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = "gemini-2.5-flash"

# Same local fetch server used in 1_local_fetch_client.py / 2_agent_fetch_client.py
server_params = StdioServerParameters(
    command="uvx",
    args=["mcp-server-fetch"],
)


async def main() -> None:
    question = "What's the newest way to get to the moon for today?"

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # This one call replaces mcp_tool_to_gemini_declaration() entirely --
            # it lists the MCP server's tools AND converts each one into a
            # LangChain-compatible tool in one shot.
            tools = await load_mcp_tools(session)

            model = ChatGoogleGenerativeAI(model=MODEL)

            # create_react_agent builds the whole "call model -> check for tool
            # calls -> run tools -> feed results back -> repeat until plain
            # text" loop for us -- that's everything our MAX_TURNS for-loop in
            # 2_agent_fetch_client.py did by hand.
            agent = create_agent(model, tools)

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": question}]} #Why don't we format the prompt here? Because it's very simple in this case?
            )

            print("\nFull message history (each tool call + result is one message):")
            for message in result["messages"]:
                print(f"- {type(message).__name__}: {str(message.content)}")

            print("\nFinal answer:")
            print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = "gemini-2.5-flash"
MAX_TURNS = 5  # safety cap so a stubborn model can't loop forever

# Same local fetch server used in 1_local_fetch_client.py
server_params = StdioServerParameters(
    command="uvx",
    args=["mcp-server-fetch"],
)


def mcp_tool_to_gemini_declaration(tool) -> types.FunctionDeclaration:
    # MCP's inputSchema is already JSON Schema, so it maps ~1:1 onto Gemini's
    # function declaration format -- just drop the $schema key, which Gemini
    # doesn't expect.
    schema = dict(tool.inputSchema)
    print(f"schema: {str(schema)}")
    schema.pop("$schema", None)
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description,
        parameters_json_schema=schema,
    )


async def main() -> None:
    question = "What's the newest way to get to the moon for today?"

    gemini = genai.Client()  # reads GEMINI_API_KEY from the environment/.env

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            tool_config = types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        function_declarations=[
                            mcp_tool_to_gemini_declaration(t) for t in mcp_tools
                        ]
                    )
                ],
                # We call the MCP tool ourselves -- don't let the SDK try to
                # execute a Python function on our behalf.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )

            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=question)])
            ]

            for turn in range(1, MAX_TURNS + 1):
                response = gemini.models.generate_content(
                    model=MODEL, contents=contents, config=tool_config
                )

                if not response.function_calls:
                    print("\nFinal answer:")
                    print(response.text)
                    return

                # Replay the model's own turn back into history before adding
                # our tool results -- it may ask for several tool calls at
                # once, all living in this one content's parts.
                contents.append(response.candidates[0].content)

                for call in response.function_calls:
                    print(f"\n[turn {turn}] Gemini wants to call: {call.name}({call.args})")
                    tool_result = await session.call_tool(call.name, call.args)
                    result_text = tool_result.content[0].text
                    print(f"MCP server responded with {len(result_text)} chars of content.")

                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=call.name, response={"result": result_text}
                                )
                            ],
                        )
                    )

            print(f"\nGave up after {MAX_TURNS} turns without a genuine final answer.")


if __name__ == "__main__":
    asyncio.run(main())

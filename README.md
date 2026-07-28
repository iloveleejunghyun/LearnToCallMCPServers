# LearnToCallMCPServers

Learn MCP (Model Context Protocol) hands-on, by running increasingly real projects instead of just reading the spec. Each script is small, runnable on its own, and adds exactly one new concept on top of the last one.

## Setup

You need [`uv`](https://docs.astral.sh/uv/) installed (it manages both the Python version and dependencies here — no separate `pip install` needed).

```bash
uv sync
```

Then create a `.env` file in this directory with whatever the scripts you're running need (see each section below for which keys):

```bash
GOOGLE_API_KEY=...          # for scripts 2 and 3 (Gemini)
GITHUB_OAUTH_CLIENT_ID=...  # for scripts 5, 6, 7 (GitHub OAuth)
GITHUB_OAUTH_CLIENT_SECRET=...

# Only needed if you're behind a proxy to reach the internet:
http_proxy=http://127.0.0.1:PORT
https_proxy=http://127.0.0.1:PORT
no_proxy=localhost,127.0.0.1   # important: without this, requests to your
                                # own localhost servers get routed through
                                # the proxy too, and fail
```

`.env` is gitignored — never commit it.

## The scripts, in order

Run any of them with `uv run <filename>`.

### 1. [`1_local_fetch_client.py`](1_local_fetch_client.py) — your first MCP client
Spawns a **local** MCP server (`mcp-server-fetch`, via `uvx`) as a subprocess and talks to it over stdio — the standard transport for local servers. Lists its tools, then calls one directly, with the tool name and arguments hardcoded by *you*, not chosen by an LLM.

**What it teaches:** the actual client-server lifecycle — spawning a server, the `initialize()` handshake, `list_tools()`, `call_tool()`. No AI involved yet; this is pure protocol mechanics.

### 2. [`2_agent_fetch_client.py`](2_agent_fetch_client.py) — a real agent loop
Same local fetch server, but now an LLM (Gemini, via the raw `google-genai` SDK) decides which tool to call and with what arguments — you just wire its decision to the MCP server and feed the result back. Runs in a loop until the model produces a final answer with no more tool calls left.

**What it teaches:** how MCP tool schemas become LLM function-calling schemas, why you have to manually replay the model's own turn back into the conversation (the API is stateless), and why the loop can't just run a fixed number of times — it has to keep going until the model is *actually* done.

### 3. [`3_langchain_agent_fetch_client.py`](3_langchain_agent_fetch_client.py) — the same thing, with a framework
Rebuilds exactly what script 2 does, but using LangChain/LangGraph (`load_mcp_tools` + `create_agent`) instead of hand-rolled SDK calls.

**What it teaches:** what a framework actually buys you (no more hand-written agent loop, automatic tool-schema conversion) versus what it costs you (an extra layer between you and what's really happening on the wire — worth comparing side-by-side with script 2 rather than picking one and never looking back).

### 4. [`4_remote_deepwiki_client.py`](4_remote_deepwiki_client.py) — your first remote server
Connects to a **remote** MCP server over plain HTTP (DeepWiki, public, no login required) instead of spawning a local process.

**What it teaches:** the Streamable HTTP transport, and that "remote" really just means a different transport underneath the same `ClientSession` API — everything else about calling tools stays the same.

### 5. [`5_remote_github_oauth_client.py`](5_remote_github_oauth_client.py) — a remote server that needs real OAuth
Connects to GitHub's real, official remote MCP server, which requires actual OAuth login (authorization code + PKCE) — not the toy kind, the real GitHub consent screen. **Requires setup**: create a GitHub OAuth App (Settings → Developer settings → OAuth Apps → New OAuth App), callback URL `http://localhost:3030/callback`, put the Client ID/Secret in `.env`.

**What it teaches:** the full OAuth authorization-code + PKCE flow end to end — why a short-lived code exists instead of handing back the token directly, why a local callback server is needed, and (via `GitHubOAuthClientProvider`) a real-world quirk where GitHub's token endpoint doesn't follow the RFC 6749 default.

### 6 & 7. [`6_github_oauth_backend_server.py`](6_github_oauth_backend_server.py) + [`7_github_oauth_backend_client.py`](7_github_oauth_backend_client.py) — splitting client from backend
Same GitHub OAuth App as script 5, but now split across two processes: a real backend server that holds the GitHub `client_secret` and the resulting access token, and a thin client that knows *nothing* about GitHub at all — it only ever talks to your own backend, and only ever holds a session token scoped to that backend. Run the server first (leave it running), then run the client in a second terminal.

**What it teaches:** the difference between a "public client" (script 5 — can't keep a secret, so it leans on PKCE) and a "confidential client" (script 6 — has a real secret, held server-side, never distributed). This is also the architecture behind "connect your GitHub account" buttons on real products: the product's backend holds your token, not your browser.

## Suggested path

If you're starting from zero: **1 → 2 → 4 → 5 → 6/7**, then loop back to **3** once you want to see what a framework changes. Scripts 1-4 are standalone; 5 and 6/7 both need the GitHub OAuth App setup described in script 5's section above (6/7 reuse the same app).

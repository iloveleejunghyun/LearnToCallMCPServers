'''
This is a public client since it stores everything on its own.

'''

import asyncio
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

load_dotenv()

# Unlike DeepWiki, GitHub's remote MCP server requires "manual client
# provisioning" -- it doesn't support Dynamic Client Registration, so we
# pre-supply an OAuth App's credentials instead of letting the SDK register
# a new client on the fly.
SERVER_URL = "https://api.githubcopilot.com/mcp/"
REDIRECT_PORT = 3030
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

CLIENT_ID = os.environ["GITHUB_OAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["GITHUB_OAUTH_CLIENT_SECRET"] # The secret is just theater since it's store in the user's side.


class _CallbackHandler(BaseHTTPRequestHandler):
    """Catches GitHub's redirect back to http://localhost:3030/callback."""

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            self.server.auth_code = params["code"][0]  # type: ignore[attr-defined]
            self.server.auth_state = params.get("state", [None])[0]  # type: ignore[attr-defined]
            body = b"<html><body>Authorized! You can close this tab and return to the terminal.</body></html>"
            self.send_response(200)
        else:
            self.server.auth_error = params.get("error", ["unknown_error"])[0]  # type: ignore[attr-defined]
            body = b"<html><body>Authorization failed. Check the terminal.</body></html>"
            self.send_response(400)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 -- silence default request logging
        pass


class InMemoryTokenStorage(TokenStorage):
    """Holds our pre-registered OAuth App's credentials plus whatever access
    token we get back -- all in process memory, nothing written to disk."""

    def __init__(self, client_id: str, client_secret: str):
        self._tokens: OAuthToken | None = None
        self._client_info = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=[REDIRECT_URI],  # type: ignore[list-item]
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )

    async def get_tokens(self) -> OAuthToken | None: # async?
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        # Returning a populated client here is what makes OAuthClientProvider
        # skip Dynamic Client Registration entirely and go straight to
        # requesting authorization.
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


class GitHubOAuthClientProvider(OAuthClientProvider):
    """GitHub's token endpoint returns application/x-www-form-urlencoded
    by default (e.g. "access_token=...&token_type=bearer"), but the base
    SDK expects JSON per RFC 6749. Explicitly asking for JSON via the
    Accept header makes GitHub return the spec-compliant format."""

    async def _exchange_token_authorization_code(self, *args, **kwargs) -> httpx.Request:
        request = await super()._exchange_token_authorization_code(*args, **kwargs)
        request.headers["Accept"] = "application/json"
        return request

    async def _refresh_token(self) -> httpx.Request:
        request = await super()._refresh_token()
        request.headers["Accept"] = "application/json"
        return request


async def redirect_handler(auth_url: str) -> None:
    print(f"\nOpening your browser to authorize with GitHub:\n{auth_url}\n")
    webbrowser.open(auth_url)


async def callback_handler() -> tuple[str, str | None]:
    """Spins up a throwaway local HTTP server just long enough to catch the
    redirect GitHub sends back after you click Authorize."""
    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler) #Why do we need a server? To receive the auth result / the access token from github
    server.auth_code = None  # type: ignore[attr-defined]
    server.auth_state = None  # type: ignore[attr-defined]
    server.auth_error = None  # type: ignore[attr-defined]

    thread = threading.Thread(target=server.serve_forever, daemon=True) #Do I have to create a local server in the front if the client doesn't have a backend server?
    thread.start()
    print(f"Listening for GitHub's OAuth callback on {REDIRECT_URI} ...")

    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            if server.auth_code:  # type: ignore[attr-defined]
                return server.auth_code, server.auth_state  # type: ignore[attr-defined]
            if server.auth_error:  # type: ignore[attr-defined]
                raise RuntimeError(f"OAuth error from GitHub: {server.auth_error}")  # type: ignore[attr-defined]
            await asyncio.sleep(0.2)
        raise TimeoutError("Timed out waiting for you to authorize in the browser")
    finally:
        server.shutdown()
        thread.join(timeout=1)


async def main() -> None:
    oauth_provider = GitHubOAuthClientProvider(
        server_url=SERVER_URL,
        client_metadata=OAuthClientMetadata(
            client_name="LearnToCallMCPServers demo",
            redirect_uris=[REDIRECT_URI],  # type: ignore[list-item]
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_post",
        ),
        storage=InMemoryTokenStorage(CLIENT_ID, CLIENT_SECRET),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    async with streamablehttp_client(SERVER_URL, auth=oauth_provider) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"\nAuthorized! GitHub's remote MCP server exposes {len(tools.tools)} tools, e.g.:")
            for tool in tools.tools[:10]:
                print(f"- {tool.name}: {tool.description[:80]}")

            result = await session.call_tool("get_me", {})
            print("\nResult of calling `get_me` (proof the token actually works):")
            print(result.content[0].text[:500])


if __name__ == "__main__":
    asyncio.run(main())

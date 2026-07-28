import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

CLIENT_ID = os.environ["GITHUB_OAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["GITHUB_OAUTH_CLIENT_SECRET"]
# Reusing the exact redirect URI already registered on the OAuth App from
# 5_remote_github_oauth_client.py -- classic GitHub OAuth Apps only support one
# callback URL, so this backend just takes over that same slot.
REDIRECT_URI = "http://localhost:3030/callback" # Do we need to send this to the client?
GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/" #Who connects to the MCP server?

app = FastAPI()

# Single-process, in-memory only -- fine for a demo, not for production:
# - PENDING_STATES: state -> PKCE code_verifier, while a login is in flight
# - SESSIONS: our own session_token -> the real GitHub access token
# The GitHub access token NEVER leaves this process.
PENDING_STATES: dict[str, str] = {}
SESSIONS: dict[str, str] = {}


#It's based on: We trust the auth server while we don't trust the client.
#Why don't we have pkce in 5_remote_github_client?
def _generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128] #What does it do? a random string with 128 chars?
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge

#Do we use the same token for github authentication, mcp server authentication and our own app authentication?
@app.get("/login") # GET method? I think it should be POST.
def login() -> RedirectResponse:
    """The client is sent here to start a GitHub login. Notice it needs no
    query params, no client_id -- the client doesn't know GitHub is even
    involved."""
    state = secrets.token_urlsafe(16) #Isn't it an enum? Why do we call it state? It's not used as a state.
    verifier, challenge = _generate_pkce_pair()
    PENDING_STATES[state] = verifier # state is the key to verifier actually. It's how we get verifier later.

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge, #We return chanllenge to the user's browser while keeping verifier in the backend.
                                    #Do we send the challenge to github? Yes.
        "code_challenge_method": "S256", #Do we send the challenge method to github? Theriatically, we can send this through getting access_token method.
        "scope": "read:user",
    }
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{urlencode(params)}") # We return this to the browser rather than the client.


@app.get("/callback") #POST?
async def callback(code: str, state: str) -> HTMLResponse:
    """GitHub redirects here after you click Authorize. Unlike the local
    throwaway server in 5_remote_github_oauth_client.py, this is just a normal
    route on a server that's always running."""
    verifier = PENDING_STATES.pop(state, None) #We use it only for once?
    if verifier is None:
        raise HTTPException(400, "Unknown or expired state")

    async with httpx.AsyncClient() as client:
        resp = await client.post( # Why do we use async http request here and await? Because there may be multiple "callback" requests occupying the same thread. If we don't use async and await, current thread will be blocked by one of the requsts and we can't handle other reqs at the same time.
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,  # never leaves this backend
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
    token_data = resp.json()
    if "access_token" not in token_data:
        raise HTTPException(400, f"GitHub token exchange failed: {token_data}")

    github_token = token_data["access_token"]
    session_token = secrets.token_urlsafe(32) #A random string? 
    SESSIONS[session_token] = github_token #session_token is actually the key for github token? Why do we call it token? It's not used as a token.

    # Same-machine demo hand-off: write our session token where the client
    # script can pick it up. A real app would set a cookie or return this
    # from a proper login API instead.
    with open(".backend_session", "w") as f:
        f.write(session_token) #It simulates a database to store access tokens here

    return HTMLResponse(
        "<html><body><h1>Logged in!</h1>"
        "<p>Your backend session is ready. Go back to the client terminal.</p>"
        "</body></html>"
    )


@app.get("/api/whoami")
async def whoami(authorization: str = Header(...)) -> dict:
    """The only endpoint the client actually calls. It authenticates with
    OUR session token -- never a GitHub token. This backend is the only
    thing that ever touches the real GitHub credential, and it uses it
    here to call GitHub's MCP server on the client's behalf."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer session token")
    session_token = authorization.removeprefix("Bearer ")
    github_token = SESSIONS.get(session_token)
    if github_token is None:
        raise HTTPException(401, "Invalid or expired session")

 
    async with streamablehttp_client(
        GITHUB_MCP_URL, headers={"Authorization": f"Bearer {github_token}"}
    ) as (read, write, _):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()  # no list_tools() needed -- we already know we want "get_me"
            result = await mcp_session.call_tool("get_me", {})
            return {"result": result.content[0].text}



if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=3030)

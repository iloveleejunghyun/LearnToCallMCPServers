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
REDIRECT_URI = "http://localhost:3030/callback"  # server-side only -- the client never sees or needs this
GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"  # only this backend connects here, inside whoami() -- the client never touches GitHub at all

app = FastAPI()

# Single-process, in-memory only -- fine for a demo, not for production:
# - PENDING_STATES: state -> PKCE code_verifier, while a login is in flight
# - SESSIONS: our own session_token -> the real GitHub access token
# The GitHub access token NEVER leaves this process.
PENDING_STATES: dict[str, str] = {}
SESSIONS: dict[str, str] = {}


# PKCE exists because the auth server can't tell, from the code alone,
# whether whoever redeems it is really the same party that started the
# flow -- it binds the code to a secret (verifier) only we ever held.
# 5_remote_github_oauth_client.py DOES have PKCE too -- it's just generated
# inside OAuthClientProvider (the SDK), invisible in that file. Here we do
# raw OAuth by hand, so it's code we write and can see instead.
def _generate_pkce_pair() -> tuple[str, str]:
    # token_urlsafe(64) actually yields ~86 chars, not 128 -- the [:128] slice
    # never truncates anything (86 < 128), just defensive since PKCE requires 43-128.
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge

# Two tokens now, not one: the real GitHub token (used for BOTH GitHub API
# auth and MCP server auth, same reasoning as before) lives only in this
# backend; session_token below is a totally separate, unrelated credential
# for client<->backend auth, with zero connection to GitHub's OAuth system.
@app.get("/login")  # must be GET -- OAuth's authorize endpoint is designed to be navigated to via browser redirect, which only works with GET
def login() -> RedirectResponse:
    """The client is sent here to start a GitHub login. Notice it needs no
    query params, no client_id -- the client doesn't know GitHub is even
    involved."""
    # Not an enum -- "state" is RFC 6749 terminology for a CSRF-protection
    # nonce, not a status value. It proves this callback really came from a
    # login WE started, not an attacker tricking your browser into hitting
    # our /callback with their own code.
    state = secrets.token_urlsafe(16)
    verifier, challenge = _generate_pkce_pair()
    PENDING_STATES[state] = verifier  # yes -- state is literally the dict key we use to look verifier back up later

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        # challenge (a hash) goes to GitHub now, in this URL; verifier (the
        # actual secret) stays here and only gets sent later, at /callback.
        "code_challenge": challenge,
        # Must be declared upfront, not deferred to the token step: GitHub
        # stores (challenge, method) tied to the code the moment it's issued,
        # so it needs to already know which hash function to check against.
        "code_challenge_method": "S256",
        "scope": "read:user",
    }
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{urlencode(params)}")  # goes to the browser GitHub redirected -- the client process never sees this URL


@app.get("/callback")  # must be GET -- same reason as /login, GitHub's redirect always arrives as a GET
async def callback(code: str, state: str) -> HTMLResponse:
    """GitHub redirects here after you click Authorize. Unlike the local
    throwaway server in 5_remote_github_oauth_client.py, this is just a normal
    route on a server that's always running."""
    verifier = PENDING_STATES.pop(state, None)  # yes, exactly once -- .pop() removes it, so replaying this URL a 2nd time fails (anti-replay)
    if verifier is None:
        raise HTTPException(400, "Unknown or expired state")

    async with httpx.AsyncClient() as client:
        # Correct instinct: async here means one slow call to github.com
        # doesn't block this whole server from handling any other request
        # concurrently (other users logging in, other endpoints, etc.).
        resp = await client.post(
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
    session_token = secrets.token_urlsafe(32)  # yes, a cryptographically random string
    # It IS a real token: the client presents it as `Authorization: Bearer
    # <session_token>` to prove its identity, same role any bearer token
    # plays. Using it as a dict key too is just our lookup mechanism -- that
    # doesn't disqualify it from being a token, same as a session cookie's
    # value often doubling as a DB row's primary key.
    SESSIONS[session_token] = github_token

    # Same-machine demo hand-off: write our session token where the client
    # script can pick it up. A real app would set a cookie or return this
    # from a proper login API instead. NOTE: this file is NOT "the database"
    # -- SESSIONS (above) is; this file is just a one-time channel to get
    # one session_token from this process to the separate client process,
    # closer to "simulating a cookie landing in a browser."
    with open(".backend_session", "w") as f:
        f.write(session_token)

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

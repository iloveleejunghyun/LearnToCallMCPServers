import time
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

import httpx

load_dotenv()

BACKEND_URL = "http://localhost:3030"
# Fair to feel weird about this -- it IS a demo shortcut, not how a real app
# would do it. A real app wouldn't need this file at all: the browser itself
# would carry a session cookie set during /callback, and there'd be no
# separate client script polling for one. This file only exists because
# these are two separate OS processes on the same machine that otherwise
# have no way to share state.
SESSION_FILE = Path(".backend_session")


def wait_for_session(timeout: float = 120) -> str:
    SESSION_FILE.unlink(missing_ok=True)  # Path.unlink() deletes the file; ignore a stale session from a previous run
    deadline = time.time() + timeout
    while time.time() < deadline:
        if SESSION_FILE.exists():
            return SESSION_FILE.read_text().strip()
        time.sleep(0.3)
    raise TimeoutError("Timed out waiting for login")


def main() -> None:
    # Notice: no client_id, no client_secret, no PKCE, no GitHub URLs
    # anywhere in this file. This client doesn't know GitHub is involved.
    print(f"Opening {BACKEND_URL}/login ...")
    webbrowser.open(f"{BACKEND_URL}/login")  # returns instantly -- the actual gap before the session file appears is real network + browser round-trip time (GitHub render/redirect, our /callback, the token exchange)

    session_token = wait_for_session()
    print(f"\nGot our own session token from the backend: {session_token[:12]}...")  # correct instinct -- never log full tokens/secrets, even non-GitHub ones
    print("(This is NOT a GitHub token -- this client will never see one.)")

    resp = httpx.get(
        f"{BACKEND_URL}/api/whoami",
        headers={"Authorization": f"Bearer {session_token}"},
        timeout=30,
    )
    resp.raise_for_status()  # raises httpx.HTTPStatusError for a 4xx/5xx response; silent no-op for 2xx/3xx
    print("\nBackend's response (it made the real GitHub call on our behalf):")
    print(resp.json())


if __name__ == "__main__":
    main()

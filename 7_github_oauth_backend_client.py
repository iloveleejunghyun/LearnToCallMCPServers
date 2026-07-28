import time
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

import httpx

load_dotenv()

BACKEND_URL = "http://localhost:3030"
SESSION_FILE = Path(".backend_session") #I feel weired. Because we should get the token from login. Is it hard to get in this demo?


def wait_for_session(timeout: float = 120) -> str:
    #unlink ?
    SESSION_FILE.unlink(missing_ok=True)  # ignore a stale session from a previous run
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
    webbrowser.open(f"{BACKEND_URL}/login") #We get the result of login real quick. But we have to wait for the session token.

    session_token = wait_for_session()
    print(f"\nGot our own session token from the backend: {session_token[:12]}...") # We should never log the full tokens/secrets for security.
    print("(This is NOT a GitHub token -- this client will never see one.)")

    resp = httpx.get(
        f"{BACKEND_URL}/api/whoami",
        headers={"Authorization": f"Bearer {session_token}"},
        timeout=30,
    )
    resp.raise_for_status() # What does it do?
    print("\nBackend's response (it made the real GitHub call on our behalf):")
    print(resp.json())


if __name__ == "__main__":
    main()

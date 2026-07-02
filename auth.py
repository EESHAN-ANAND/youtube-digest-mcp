"""OAuth authentication for the YouTube digest MCP server.

Handles the one-time Google login and reuses/refreshes the saved token so you
only ever have to approve access once (browser opens on first run).

Run directly to perform the login and verify it worked:

    uv run python auth.py
"""

import json
import os

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

# Read-only access: the server can read your subscriptions/videos but can never
# post, comment, subscribe, or change anything on your account.
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

_BASE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE", os.path.join(_BASE, "client_secret.json"))
TOKEN_FILE = os.getenv("TOKEN_FILE", os.path.join(_BASE, "token.json"))


def get_credentials() -> Credentials:
    """Return valid OAuth credentials.

    Two modes:
    - CLOUD/headless: if GOOGLE_TOKEN_JSON env var is set (the contents of a
      token.json produced by a local login), build credentials from it and
      refresh silently — no browser needed.
    - LOCAL: use token.json on disk, or run the one-time browser login flow.
    """
    # Cloud/headless path: token supplied via environment variable.
    token_json = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise RuntimeError(
                    "GOOGLE_TOKEN_JSON is invalid/expired and cannot refresh. "
                    "Re-run the local login and update the env var."
                )
        return creds

    # Local path: file on disk, or interactive browser login.
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Token expired but we have a refresh token -> renew silently.
            creds.refresh(Request())
        else:
            # No token (or unrecoverable) -> open the browser consent flow.
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Persist the (new/refreshed) token for next time.
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def get_youtube():
    """Return an authenticated YouTube Data API v3 client."""
    return build("youtube", "v3", credentials=get_credentials())


if __name__ == "__main__":
    youtube = get_youtube()
    # Verify the login by reading the authenticated user's own channel.
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if items:
        print(f"✅ Logged in successfully as channel: {items[0]['snippet']['title']}")
    else:
        print("✅ Authenticated, but no YouTube channel is attached to this account.")
    print(f"Token saved to: {TOKEN_FILE}")

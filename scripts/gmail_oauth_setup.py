"""ONE-TIME script: walks through OAuth consent and prints the refresh token.

Prerequisites:
1. Create a Google Cloud project (free tier is fine).
2. Enable the Gmail API for that project.
3. Create OAuth 2.0 credentials of type "Desktop app".
4. Download the credentials JSON; export client_id + client_secret as env vars
   (or edit the constants below temporarily).

Run this on your laptop, NOT on Railway.

After running:
- Browser opens, you log in with the test Gmail account
- Approve the requested scopes
- The script prints the refresh token to stdout
- Copy it into Railway env vars as GMAIL_REFRESH_TOKEN
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read + label + drafts
    "https://www.googleapis.com/auth/gmail.send",    # for alert emails (if we choose Gmail SMTP)
]


def main() -> int:
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in env first.", file=sys.stderr)
        return 2

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\n=== Save these into your env / Railway vars ===")
    print(f"GMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GMAIL_USER_EMAIL={_userinfo(creds)}")
    return 0


def _userinfo(creds) -> str:
    """Best-effort fetch of the authenticated user's email; falls back to placeholder."""
    try:
        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = svc.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "unknown@example.com")
    except Exception:  # noqa: BLE001
        return "FILL_IN_MANUALLY@example.com"


if __name__ == "__main__":
    raise SystemExit(main())

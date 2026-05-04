"""Build authenticated Gmail Credentials from refresh token in env."""
import os

from google.oauth2.credentials import Credentials


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def credentials_from_env() -> Credentials:
    refresh_token = os.environ["GMAIL_REFRESH_TOKEN"]
    client_id = os.environ["GMAIL_CLIENT_ID"]
    client_secret = os.environ["GMAIL_CLIENT_SECRET"]
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )

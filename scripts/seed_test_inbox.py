"""Seed the test Gmail inbox with golden fixture emails.

Sends each fixture as an email FROM the test account TO itself. Run once before
running the golden test suite. Idempotent in the sense that you can re-run, but
note that each run creates new threads (the old ones don't go away unless you
clear them first).

Run: uv run python scripts/seed_test_inbox.py
"""
import base64
import os
from email.message import EmailMessage
from pathlib import Path

import yaml
from dotenv import load_dotenv
from googleapiclient.discovery import build

from shine_email_assistant.gmail_client.auth import credentials_from_env

load_dotenv()


def main() -> int:
    fixtures_path = Path(__file__).resolve().parent.parent / "tests/integration/golden/fixtures/golden_emails.yaml"
    fixtures = yaml.safe_load(fixtures_path.read_text())

    user_email = os.environ["GMAIL_USER_EMAIL"]
    svc = build("gmail", "v1", credentials=credentials_from_env(), cache_discovery=False)

    for fx in fixtures:
        msg = EmailMessage()
        msg["From"] = fx["from"]
        msg["To"] = user_email
        msg["Subject"] = f"[golden:{fx['id']}] {fx['subject']}"
        msg.set_content(fx["body"])
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        # Insert directly into the user's inbox; this keeps the From header as written.
        svc.users().messages().insert(
            userId="me", body={"raw": raw, "labelIds": ["INBOX", "UNREAD"]}
        ).execute()
        print(f"seeded {fx['id']}")

    print(f"\nSeeded {len(fixtures)} fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

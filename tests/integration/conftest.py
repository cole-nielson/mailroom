"""Integration test fixtures. These tests hit real Gmail/Anthropic; run sparingly."""
import os

import pytest

from shine_email_assistant.gmail_client import GmailClient


def _has_gmail_creds() -> bool:
    return all(os.getenv(k) for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "GMAIL_USER_EMAIL"))


def _has_anthropic_creds() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


@pytest.fixture
def gmail_client():
    if not _has_gmail_creds():
        pytest.skip("Gmail credentials not in env; skipping integration test.")
    return GmailClient()


@pytest.fixture
def anthropic_available():
    if not _has_anthropic_creds():
        pytest.skip("ANTHROPIC_API_KEY not set; skipping integration test.")
    return True

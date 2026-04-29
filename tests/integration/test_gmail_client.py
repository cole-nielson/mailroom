"""Smoke tests against a real test Gmail account.

These verify the Gmail wrapper actually talks to Gmail. They cost real API calls
(small) and require the test account to exist + have at least one inbox message.

Run with: uv run pytest tests/integration/test_gmail_client.py -m integration -v
"""
import pytest


pytestmark = pytest.mark.integration


def test_can_list_unprocessed_threads(gmail_client):
    ids = gmail_client.list_unprocessed_thread_ids(max_results=5)
    assert isinstance(ids, list)
    # Don't assert on length — fresh test inboxes may be empty.


def test_can_get_thread_if_any_exist(gmail_client):
    ids = gmail_client.list_unprocessed_thread_ids(max_results=1)
    if not ids:
        pytest.skip("test inbox empty; can't exercise get_thread")
    t = gmail_client.get_thread(ids[0])
    assert t.thread_id == ids[0]
    assert len(t.messages) >= 1
    latest = t.latest_message
    assert latest.from_email  # parsed
    assert latest.subject is not None


def test_can_create_and_remove_processed_label(gmail_client):
    """Verifies the label-management plumbing — uses a throwaway label name."""
    label = "shine-test-label-do-not-use"
    label_id = gmail_client._ensure_label(label)
    assert label_id
    # second call is idempotent
    assert gmail_client._ensure_label(label) == label_id


def test_can_create_and_delete_draft_on_thread(gmail_client):
    """End-to-end: list a thread, create a draft on it, delete the draft."""
    ids = gmail_client.list_unprocessed_thread_ids(max_results=1)
    if not ids:
        pytest.skip("test inbox empty; can't exercise create_draft")

    thread = gmail_client.get_thread(ids[0])
    latest = thread.latest_message
    msg_id_header = latest.headers.get("Message-ID") or latest.headers.get("Message-Id") or ""
    if not msg_id_header:
        pytest.skip("test message has no Message-ID header; can't reply")

    draft_id = gmail_client.create_draft(
        thread_id=thread.thread_id,
        in_reply_to_message_id_header=msg_id_header,
        to=latest.from_email,
        subject=latest.subject,
        html_body="<p>Test draft — please ignore.</p>",
        plaintext_body="Test draft — please ignore.",
    )
    assert draft_id

    # cleanup so we don't pollute the inbox
    gmail_client.delete_draft(draft_id)

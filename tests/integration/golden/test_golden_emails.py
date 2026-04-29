"""Run the pipeline against the seeded test inbox; assert outcomes match expectations.

Pre-req: run `uv run python scripts/seed_test_inbox.py` first.

Outcome mapping:
- "drafted"  → thread ends up with `processed` label and a DraftRecord exists
- "skipped"  → thread ends up with `processed-skipped` label and a SkipRecord exists
- "flagged"  → thread ends up with `flag-for-human` label, no DraftRecord
"""
import os
import time
from pathlib import Path

import pytest
import yaml

from shine_email_assistant.db import DraftRecord, init_db, session
from shine_email_assistant.gmail_client import (
    FLAG_FOR_HUMAN_LABEL,
    PROCESSED_LABEL,
    SKIPPED_LABEL,
    GmailClient,
)
from shine_email_assistant.pipeline import Pipeline


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fixtures():
    path = Path(__file__).parent / "fixtures/golden_emails.yaml"
    return {fx["id"]: fx for fx in yaml.safe_load(path.read_text())}


@pytest.fixture(scope="module")
def processed_threads(fixtures, gmail_client):
    """Run the pipeline once over all unprocessed threads. Returns mapping fixture_id → thread."""
    init_db()
    tenants_root = Path(__file__).resolve().parents[3] / "tenants"
    tenant = os.getenv("TENANT_NAME", "shine")

    pipeline = Pipeline(tenant_name=tenant, tenants_root=tenants_root)
    pipeline.tick()
    # Give Gmail a beat to settle label changes
    time.sleep(2)

    # Map back from thread → fixture by parsing the [golden:<id>] tag in the subject.
    out: dict[str, dict] = {}
    threads = gmail_client._service.users().threads().list(userId="me", q="subject:[golden:]").execute().get("threads", [])
    for t in threads:
        full = gmail_client.get_thread(t["id"])
        subj = full.latest_message.subject
        # Subject format: "[golden:<id>] ..."
        if subj.startswith("[golden:"):
            close = subj.find("]")
            fx_id = subj[len("[golden:"):close]
            label_names = _label_names(gmail_client, t["id"])
            out[fx_id] = {"thread_id": t["id"], "labels": label_names, "subject": subj}
    return out


def _label_names(gmail_client: GmailClient, thread_id: str) -> set[str]:
    raw = gmail_client._service.users().threads().get(userId="me", id=thread_id).execute()
    label_ids: set[str] = set()
    for m in raw.get("messages", []):
        label_ids.update(m.get("labelIds", []))
    # Reverse-lookup label IDs to names
    all_labels = gmail_client._service.users().labels().list(userId="me").execute().get("labels", [])
    by_id = {l["id"]: l["name"] for l in all_labels}
    return {by_id[lid] for lid in label_ids if lid in by_id}


@pytest.mark.parametrize("fixture_id", [
    "schedule_question_simple",
    "pricing_drop_in",
    "beginner_inquiry",
    "refund_request",
    "complaint",
    "vendor_pitch",
    "short_thanks",
    "ambiguous_multi_question",
    "registration",
    "family_question",
])
def test_golden_email_outcome(fixture_id, fixtures, processed_threads):
    fixture = fixtures[fixture_id]
    if fixture_id not in processed_threads:
        pytest.skip(f"fixture {fixture_id} not in inbox; re-run scripts/seed_test_inbox.py")

    info = processed_threads[fixture_id]
    expected = fixture["expected_outcome"]

    if expected == "drafted":
        assert PROCESSED_LABEL in info["labels"], f"{fixture_id}: expected processed, got {info['labels']}"
        with session() as s:
            row = s.query(DraftRecord).filter(DraftRecord.thread_id == info["thread_id"]).first()
        assert row is not None, f"{fixture_id}: no DraftRecord"
        if "expected_category_substring" in fixture:
            assert fixture["expected_category_substring"] in row.category.lower()
    elif expected == "skipped":
        assert SKIPPED_LABEL in info["labels"], f"{fixture_id}: expected skipped, got {info['labels']}"
    elif expected == "flagged":
        assert FLAG_FOR_HUMAN_LABEL in info["labels"], f"{fixture_id}: expected flagged, got {info['labels']}"
        with session() as s:
            row = s.query(DraftRecord).filter(DraftRecord.thread_id == info["thread_id"]).first()
        assert row is None, f"{fixture_id}: DraftRecord should not exist for flagged"
    else:
        pytest.fail(f"unknown expected_outcome: {expected}")

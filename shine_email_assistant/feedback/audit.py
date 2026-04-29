"""Daily sweep: compare each recent draft to the actually-sent message in the thread."""
from datetime import datetime, timedelta, timezone

from shine_email_assistant.db import DraftRecord, session
from shine_email_assistant.feedback.diff import categorize_outcome, edit_distance_ratio
from shine_email_assistant.gmail_client import GmailClient
from shine_email_assistant.log import get_logger

log = get_logger(__name__)


def audit_recent_drafts(*, hours: int = 30) -> dict:
    """For each draft created in the last N hours that hasn't been audited, find the
    sent message in the same thread (if any), compute edit distance, persist outcome.

    Returns a summary dict (counts by outcome).
    """
    gmail = GmailClient()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    summary = {"sent_as_is": 0, "lightly_edited": 0, "heavily_rewritten": 0, "not_sent": 0, "audited": 0}

    with session() as s:
        rows = s.query(DraftRecord).filter(
            DraftRecord.audited_at.is_(None),
            DraftRecord.created_at >= cutoff.replace(tzinfo=None),  # naive UTC in DB
        ).all()

        # Pre-fetch recent sent messages once
        sent_by_thread: dict[str, list[dict]] = {}
        for sm in gmail.list_recent_sent_messages(hours=hours + 24):
            sent_by_thread.setdefault(sm["threadId"], []).append(sm)

        for row in rows:
            sent_msgs = sent_by_thread.get(row.thread_id, [])
            # Filter to sent messages after the draft was created, then pick the earliest.
            # internalDate is a string of ms since epoch. row.created_at is naive UTC.
            draft_ms = int(row.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            after_draft = [sm for sm in sent_msgs if int(sm.get("internalDate", 0)) >= draft_ms]
            chosen = min(after_draft, key=lambda sm: int(sm["internalDate"]), default=None)

            if not chosen:
                row.outcome = "not_sent"
                row.audited_at = datetime.now(timezone.utc).replace(tzinfo=None)
                summary["not_sent"] += 1
                summary["audited"] += 1
                continue

            try:
                sent_text = gmail.get_message_body_text(chosen["id"])
            except Exception as e:  # noqa: BLE001
                log.warning("audit_fetch_failed", message_id=chosen["id"], error=str(e))
                row.outcome = "audit_fetch_failed"
                row.audited_at = datetime.now(timezone.utc).replace(tzinfo=None)
                summary["audited"] += 1
                continue

            ratio = edit_distance_ratio(row.body_markdown.strip(), sent_text.strip())
            outcome = categorize_outcome(ratio)
            row.outcome = outcome.value
            row.edit_distance_ratio = ratio
            row.sent_message_id = chosen["id"]
            row.audited_at = datetime.now(timezone.utc).replace(tzinfo=None)
            summary[outcome.value] += 1
            summary["audited"] += 1

        s.commit()

    log.info("audit_complete", **summary)
    return summary

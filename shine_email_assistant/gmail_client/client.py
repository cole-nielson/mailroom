"""Gmail API wrapper. Only the operations the pipeline actually needs."""
import base64
import os
import re
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Iterable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from shine_email_assistant.gmail_client.auth import credentials_from_env
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread
from shine_email_assistant.log import get_logger

log = get_logger(__name__)


PROCESSED_LABEL = "processed"
SKIPPED_LABEL = "processed-skipped"
ERROR_LABEL = "draft-error"
FLAG_FOR_HUMAN_LABEL = "flag-for-human"


class GmailClient:
    """Single source of truth for Gmail API calls."""

    def __init__(self, user_email: str | None = None):
        self._user_email = (user_email or os.environ["GMAIL_USER_EMAIL"]).lower()
        self._service = build("gmail", "v1", credentials=credentials_from_env(), cache_discovery=False)
        self._label_cache: dict[str, str] = {}

    # ---- threads ----

    def list_unprocessed_thread_ids(self, max_results: int = 50) -> list[str]:
        """Return thread IDs not labeled processed/skipped/error and not in Promotions/Updates."""
        # Gmail's `q` query language.
        q = (
            f"-label:{PROCESSED_LABEL} "
            f"-label:{SKIPPED_LABEL} "
            f"-label:{ERROR_LABEL} "
            f"-label:{FLAG_FOR_HUMAN_LABEL} "
            "-category:promotions "
            "-category:updates "
            "in:inbox"
        )
        resp = self._service.users().threads().list(
            userId="me", q=q, maxResults=max_results
        ).execute()
        return [t["id"] for t in resp.get("threads", [])]

    def get_thread(self, thread_id: str) -> ParsedThread:
        raw = self._service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()

        messages = tuple(self._parse_message(m) for m in raw.get("messages", []))
        has_existing_human_draft = self._thread_has_user_draft(thread_id)

        return ParsedThread(
            thread_id=thread_id,
            messages=messages,
            has_existing_human_draft=has_existing_human_draft,
        )

    def list_recent_sent_messages(self, hours: int = 30) -> list[dict]:
        """Used by feedback sweep. Returns dicts with id, threadId, internalDate (ms since epoch as str)."""
        after = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
        q = f"in:sent after:{after}"
        resp = self._service.users().messages().list(
            userId="me",
            q=q,
            maxResults=200,
            fields="messages(id,threadId,internalDate),nextPageToken",
        ).execute()
        return resp.get("messages", [])

    def get_message_body_text(self, message_id: str) -> str:
        """Used by feedback sweep to compare drafts vs sent text."""
        raw = self._service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        return _extract_plain_text(raw.get("payload", {}))

    def create_draft(
        self,
        thread_id: str,
        in_reply_to_message_id_header: str,
        to: str,
        subject: str,
        html_body: str,
        plaintext_body: str,
        references: str | None = None,
    ) -> str:
        """Create a draft attached to an existing thread, replying to a specific message.

        Returns the new draft's ID.
        """
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        msg["In-Reply-To"] = in_reply_to_message_id_header
        msg["References"] = references or in_reply_to_message_id_header
        msg.set_content(plaintext_body)
        msg.add_alternative(html_body, subtype="html")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        body = {"message": {"raw": raw, "threadId": thread_id}}

        created = self._service.users().drafts().create(userId="me", body=body).execute()
        return created["id"]

    def delete_draft(self, draft_id: str) -> None:
        """Used by integration tests to clean up after themselves."""
        try:
            self._service.users().drafts().delete(userId="me", id=draft_id).execute()
        except HttpError as e:
            log.warning("draft_delete_failed", draft_id=draft_id, error=str(e))

    # ---- labels ----

    def add_label(self, thread_id: str, label_name: str) -> None:
        label_id = self._ensure_label(label_name)
        self._service.users().threads().modify(
            userId="me", id=thread_id, body={"addLabelIds": [label_id]}
        ).execute()

    def _ensure_label(self, name: str) -> str:
        if name in self._label_cache:
            return self._label_cache[name]
        existing = self._service.users().labels().list(userId="me").execute().get("labels", [])
        for lbl in existing:
            if lbl["name"] == name:
                self._label_cache[name] = lbl["id"]
                return lbl["id"]
        # create
        created = self._service.users().labels().create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).execute()
        self._label_cache[name] = created["id"]
        return created["id"]

    # ---- internals ----

    def _thread_has_user_draft(self, thread_id: str) -> bool:
        """True if there's an existing draft on the thread that *we* didn't create.

        For the PoC we treat ANY existing draft as "human, hands off." The trade-off:
        if our own previous draft sticks around, we won't redraft. That's fine — Dad
        will deal with it on his own schedule.
        """
        drafts = self._service.users().drafts().list(userId="me").execute().get("drafts", [])
        for d in drafts:
            if d.get("message", {}).get("threadId") == thread_id:
                return True
        return False

    def _parse_message(self, raw: dict) -> ParsedMessage:
        payload = raw.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        from_raw = headers.get("From", "")
        from_emails = [addr for _, addr in getaddresses([from_raw])]
        from_email = (from_emails[0] if from_emails else "").lower()

        to_raw = headers.get("To", "")
        to_addresses = tuple(addr for _, addr in getaddresses([to_raw]))

        date_raw = headers.get("Date")
        try:
            date = parsedate_to_datetime(date_raw) if date_raw else datetime.now(timezone.utc)
        except (TypeError, ValueError):
            date = datetime.now(timezone.utc)

        body_text = _extract_plain_text(payload)
        body_html = _extract_html(payload)

        is_from_us = from_email == self._user_email

        return ParsedMessage(
            message_id=raw["id"],
            from_address=from_raw,
            from_email=from_email,
            to_addresses=to_addresses,
            subject=headers.get("Subject", ""),
            date=date,
            headers=headers,
            body_text=body_text,
            body_html=body_html,
            is_from_us=is_from_us,
        )


# ---- payload parsing helpers ----

def _walk_parts(payload: dict) -> Iterable[dict]:
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _extract_plain_text(payload: dict) -> str:
    for part in _walk_parts(payload):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    # fall back to stripping HTML
    html = _extract_html(payload)
    if html:
        return re.sub(r"<[^>]+>", "", html)
    return ""


def _extract_html(payload: dict) -> str:
    for part in _walk_parts(payload):
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""

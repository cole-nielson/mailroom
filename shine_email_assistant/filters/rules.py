"""Cheap rule-based pre-filter. Skips obvious non-candidates with zero LLM cost."""
import re
from dataclasses import dataclass

from shine_email_assistant.gmail_client.thread import ParsedThread

_AUTOMATION_PATTERNS = (
    re.compile(r"^no-?reply@", re.IGNORECASE),
    re.compile(r"^do-?not-?reply@", re.IGNORECASE),
    re.compile(r"^mailer-?daemon@", re.IGNORECASE),
    re.compile(r"^postmaster@", re.IGNORECASE),
    re.compile(r"^bounce[s]?@", re.IGNORECASE),
)


@dataclass(frozen=True)
class SkipDecision:
    skip: bool
    reason: str = ""


def should_skip(thread: ParsedThread) -> SkipDecision:
    if thread.latest_is_from_us:
        return SkipDecision(skip=True, reason="latest message is from us")
    if thread.has_existing_human_draft:
        return SkipDecision(skip=True, reason="thread already has an existing draft")
    latest = thread.latest_message
    if "List-Unsubscribe" in latest.headers:
        return SkipDecision(skip=True, reason="List-Unsubscribe header present (mailing list)")
    for pattern in _AUTOMATION_PATTERNS:
        if pattern.match(latest.from_email):
            return SkipDecision(skip=True, reason=f"automation sender pattern: {latest.from_email}")
    return SkipDecision(skip=False)

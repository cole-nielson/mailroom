"""Smoke test: drafter produces a non-empty body that doesn't contain banned phrases."""
from datetime import datetime, timezone

import pytest

from shine_email_assistant.classifier.types import Classification, Sensitivity
from shine_email_assistant.drafter import generate
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle


pytestmark = pytest.mark.integration

_BANNED_PHRASES = [
    "i hope this email finds you well",
    "i hope this finds you well",
    "certainly!",
    "absolutely!",
    "feel free to",
    "as an ai",
]


_KB = KnowledgeBundle(
    kb_text="# Schedule\n\nMon, Wed, Fri 6pm. Saturday 9am beginner class.\n\n# Pricing\n\nDrop-in: $25. 10-pack: $200.\n",
    voice_text=(
        "# Voice\n\nWarm, concise, brand-genuine. Conversational. Like a real person at the studio replying.\n\n"
        "Sample: 'Hi! Yes, our Saturday 9am class is perfect for beginners — no experience needed. "
        "Drop in or grab a 10-pack if you think you'll be back.\n\nWarmly, Shine'"
    ),
    version="test",
)


def _classification() -> Classification:
    return Classification(
        should_draft=True,
        category="schedule_question",
        sensitivity=Sensitivity.LOW,
        confidence=0.95,
        reason="clear factual schedule question",
    )


def test_generate_returns_nonempty_body_without_banned_phrases(anthropic_available):
    thread = ParsedThread(
        thread_id="t1",
        messages=(ParsedMessage(
            message_id="m1",
            from_address="Cust <c@x.com>",
            from_email="c@x.com",
            to_addresses=("info@shinefitness.com",),
            subject="Class times",
            date=datetime.now(timezone.utc),
            body_text="Hi, when do classes meet on weekends?",
        ),),
    )

    draft = generate(thread, _KB, _classification())

    assert draft.body_markdown.strip()
    body_lower = draft.body_markdown.lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in body_lower, f"draft contains banned phrase: {phrase!r}"
    # body should reference the actual KB fact
    assert "saturday" in body_lower or "9" in body_lower

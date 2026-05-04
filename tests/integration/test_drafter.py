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
    "as an artificial intelligence",
    "i'm just a language model",
    "i am a language model",
]


_KB = KnowledgeBundle(
    kb_text=(
        "# Services\n\nFree roof inspections, repairs, and full replacements. "
        "Storm-damage insurance claim help.\n\n"
        "# Pricing\n\nInspections are free. Repairs $400–$2,000. "
        "Full asphalt shingle replacement on a typical 2,000 sq ft home: $11,000–$18,000.\n"
    ),
    voice_text=(
        "# Voice\n\nWarm, plain-spoken, direct. Like a second-generation owner who answers the phone himself. "
        "Short paragraphs. No salesy phrases.\n\n"
        "Sample: 'Yes — free inspection, no obligation. We typically can be out within 2–3 business days. "
        "Could you reply with your address and a couple of windows that work for you?'"
    ),
    version="test",
)


def _classification() -> Classification:
    return Classification(
        should_draft=True,
        category="general_question",
        sensitivity=Sensitivity.LOW,
        confidence=0.95,
        reason="clear factual service question",
    )


def test_generate_returns_nonempty_body_without_banned_phrases(anthropic_available):
    thread = ParsedThread(
        thread_id="t1",
        messages=(ParsedMessage(
            message_id="m1",
            from_address="Cust <c@example.com>",
            from_email="c@example.com",
            to_addresses=("info@example.com",),
            subject="Free inspection?",
            date=datetime.now(timezone.utc),
            body_text="Hi, do you do free roof inspections? I think I have storm damage.",
        ),),
    )

    draft = generate(thread, _KB, _classification())

    assert draft.body_markdown.strip()
    body_lower = draft.body_markdown.lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in body_lower, f"draft contains banned phrase: {phrase!r}"
    # em-dashes are banned per the prompt (rule 3)
    assert "—" not in draft.body_markdown
    # body should reference the actual KB facts (free inspection)
    assert "free" in body_lower or "inspection" in body_lower

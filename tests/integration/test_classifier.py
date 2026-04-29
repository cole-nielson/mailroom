"""Smoke test: classifier returns a structured Classification for a hand-crafted thread."""
from datetime import datetime, timezone

import pytest

from shine_email_assistant.classifier import Sensitivity, classify
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle


pytestmark = pytest.mark.integration


def _msg(body: str, from_email: str = "cust@example.com") -> ParsedMessage:
    return ParsedMessage(
        message_id="m1",
        from_address=f"Customer <{from_email}>",
        from_email=from_email,
        to_addresses=("info@shinefitness.com",),
        subject="Question",
        date=datetime.now(timezone.utc),
        body_text=body,
    )


_KB = KnowledgeBundle(
    kb_text="# Schedule\n\nWe hold classes Mon, Wed, Fri at 6pm.\n\n# Pricing\n\nDrop-in: $25.\n",
    voice_text="",
    version="test",
)


def test_classifies_simple_schedule_question_as_draftable(anthropic_available):
    thread = ParsedThread(thread_id="t1", messages=(_msg("What time is your Wednesday class?"),))
    result = classify(thread, _KB)
    assert result.should_draft is True
    assert result.sensitivity == Sensitivity.LOW
    assert "schedule" in result.category.lower() or result.category == "general_question"


def test_classifies_complaint_as_high_sensitivity_no_draft(anthropic_available):
    thread = ParsedThread(thread_id="t2", messages=(_msg(
        "I'm extremely upset. The instructor was rude to my daughter and I want a refund AND an apology."
    ),))
    result = classify(thread, _KB)
    assert result.sensitivity == Sensitivity.HIGH
    # The pipeline enforces no-draft when sensitivity=high regardless of should_draft;
    # the classifier may or may not also set should_draft=false. We only assert the sensitivity here.


def test_classifies_automated_email_as_not_draftable(anthropic_available):
    thread = ParsedThread(thread_id="t3", messages=(_msg(
        "Your shipment has been delivered. Track at https://...",
        from_email="noreply@shipping.com",
    ),))
    result = classify(thread, _KB)
    assert result.should_draft is False

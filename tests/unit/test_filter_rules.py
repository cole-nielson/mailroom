from datetime import datetime, timezone

from shine_email_assistant.filters.rules import SkipDecision, should_skip
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread


def _msg(**overrides) -> ParsedMessage:
    base = dict(
        message_id="m1",
        from_address="Customer <cust@example.com>",
        from_email="cust@example.com",
        to_addresses=("info@example.com",),
        subject="Question",
        date=datetime.now(timezone.utc),
        headers={},
        body_text="hi, can you come out for an estimate?",
        body_html="",
        is_from_us=False,
    )
    base.update(overrides)
    return ParsedMessage(**base)


def _thread(messages, has_existing_human_draft: bool = False) -> ParsedThread:
    return ParsedThread(thread_id="t1", messages=tuple(messages), has_existing_human_draft=has_existing_human_draft)


def test_skips_when_latest_message_is_from_us():
    decision = should_skip(_thread([_msg(is_from_us=True)]))
    assert decision.skip is True
    assert "from us" in decision.reason.lower()


def test_skips_when_thread_has_existing_draft():
    decision = should_skip(_thread([_msg()], has_existing_human_draft=True))
    assert decision.skip is True
    assert "existing draft" in decision.reason.lower()


def test_skips_when_sender_is_noreply():
    decision = should_skip(_thread([_msg(from_email="no-reply@brand.com")]))
    assert decision.skip is True
    assert "automation" in decision.reason.lower() or "noreply" in decision.reason.lower()


def test_skips_when_list_unsubscribe_header_present():
    decision = should_skip(_thread([_msg(headers={"List-Unsubscribe": "<https://...>"})]))
    assert decision.skip is True
    assert "list" in decision.reason.lower() or "unsubscribe" in decision.reason.lower()


def test_does_not_skip_a_normal_customer_email():
    decision = should_skip(_thread([_msg()]))
    assert decision.skip is False


def test_decision_is_typed():
    decision = should_skip(_thread([_msg()]))
    assert isinstance(decision, SkipDecision)


def test_skips_when_sender_is_dashed_bounce_address():
    decision = should_skip(_thread([_msg(from_email="bounce-12345@brand.com")]))
    assert decision.skip is True


def test_skips_when_sender_is_plus_bounce_address():
    decision = should_skip(_thread([_msg(from_email="bounce+user@brand.com")]))
    assert decision.skip is True


def test_latest_message_raises_on_empty_thread():
    import pytest
    from shine_email_assistant.gmail_client.thread import ParsedThread
    empty = ParsedThread(thread_id="t-empty", messages=())
    with pytest.raises(ValueError, match="t-empty"):
        _ = empty.latest_message

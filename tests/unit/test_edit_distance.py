from shine_email_assistant.feedback.diff import (
    Outcome,
    categorize_outcome,
    edit_distance_ratio,
)


def test_edit_distance_ratio_identical_is_zero():
    assert edit_distance_ratio("hello world", "hello world") == 0.0


def test_edit_distance_ratio_completely_different_is_one():
    assert edit_distance_ratio("hello", "xyz") > 0.9


def test_categorize_sent_as_is_for_tiny_changes():
    assert categorize_outcome(0.02) == Outcome.SENT_AS_IS


def test_categorize_lightly_edited():
    assert categorize_outcome(0.15) == Outcome.LIGHTLY_EDITED


def test_categorize_heavily_rewritten():
    assert categorize_outcome(0.6) == Outcome.HEAVILY_REWRITTEN

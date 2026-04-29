"""Edit-distance utilities for the feedback sweep."""
from difflib import SequenceMatcher
from enum import Enum


class Outcome(str, Enum):
    SENT_AS_IS = "sent_as_is"
    LIGHTLY_EDITED = "lightly_edited"
    HEAVILY_REWRITTEN = "heavily_rewritten"
    NOT_SENT = "not_sent"


def edit_distance_ratio(a: str, b: str) -> float:
    """Returns 0.0 (identical) to ~1.0 (totally different)."""
    if not a and not b:
        return 0.0
    similarity = SequenceMatcher(a=a, b=b).ratio()
    return 1.0 - similarity


def categorize_outcome(ratio: float) -> Outcome:
    """Buckets the edit-distance ratio into qualitative outcomes."""
    if ratio < 0.05:
        return Outcome.SENT_AS_IS
    if ratio < 0.30:
        return Outcome.LIGHTLY_EDITED
    return Outcome.HEAVILY_REWRITTEN

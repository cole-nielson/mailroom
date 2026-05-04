"""Classification output. The classifier's only contract."""
from dataclasses import dataclass
from enum import Enum


class Sensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Classification:
    should_draft: bool
    category: str  # free-form but seeded with a known taxonomy in the prompt
    sensitivity: Sensitivity
    confidence: float  # 0.0 - 1.0
    reason: str

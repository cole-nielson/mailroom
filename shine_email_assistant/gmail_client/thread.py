"""ParsedThread: structured representation of a Gmail thread.

The Gmail API gives back nested JSON with base64-encoded bodies; this dataclass
is the cleaned-up shape the rest of the system consumes.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ParsedMessage:
    message_id: str
    from_address: str  # "Name <addr@example.com>" or "addr@example.com"
    from_email: str    # bare email
    to_addresses: tuple[str, ...]
    subject: str
    date: datetime
    headers: dict[str, str] = field(default_factory=dict)
    body_text: str = ""
    body_html: str = ""
    is_from_us: bool = False  # set during parse based on configured user email


@dataclass(frozen=True)
class ParsedThread:
    thread_id: str
    messages: tuple[ParsedMessage, ...]
    has_existing_human_draft: bool = False

    @property
    def latest_message(self) -> ParsedMessage:
        return self.messages[-1]

    @property
    def latest_is_from_us(self) -> bool:
        return self.latest_message.is_from_us

"""Create all tables. Called at app startup. Idempotent."""
from shine_email_assistant.db.connection import get_engine
from shine_email_assistant.db.models import Base


def init_db() -> None:
    Base.metadata.create_all(get_engine())

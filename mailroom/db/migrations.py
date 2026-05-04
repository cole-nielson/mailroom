"""Create all tables. Called at app startup. Idempotent."""
from mailroom.db.connection import get_engine
from mailroom.db.models import Base


def init_db() -> None:
    Base.metadata.create_all(get_engine())

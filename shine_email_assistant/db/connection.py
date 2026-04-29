"""SQLAlchemy engine + session factory. One global engine."""
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def get_engine() -> Engine:
    url = os.environ["DATABASE_URL"]
    # Railway's Postgres add-on injects postgresql://, but SQLAlchemy 2 + psycopg3
    # needs the explicit driver in the URL. Normalize transparently.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def session() -> Session:
    return _session_factory()()

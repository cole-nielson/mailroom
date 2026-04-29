"""SQLAlchemy models. Single source of truth for DB schema."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DraftRecord(Base):
    """One row per draft we created. Updated by feedback sweep with outcome."""
    __tablename__ = "draft_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    draft_id: Mapped[str] = mapped_column(String(128))
    message_id_replied_to: Mapped[str] = mapped_column(String(256))

    # Classification snapshot
    category: Mapped[str] = mapped_column(String(64), index=True)
    sensitivity: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column()
    classification_reason: Mapped[str] = mapped_column(Text)

    # Drafted content
    body_markdown: Mapped[str] = mapped_column(Text)
    rendered_html: Mapped[str] = mapped_column(Text)

    # Provenance
    kb_version: Mapped[str] = mapped_column(String(64))  # hash of KB content used
    model_used: Mapped[str] = mapped_column(String(64))
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Filled by feedback sweep
    outcome: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # one of: "sent_as_is" | "lightly_edited" | "heavily_rewritten" | "not_sent" | None (not yet audited)
    edit_distance_ratio: Mapped[Optional[float]] = mapped_column(nullable=True)
    sent_message_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    audited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SkipRecord(Base):
    """One row per email we decided not to draft. For tuning."""
    __tablename__ = "skip_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    skip_source: Mapped[str] = mapped_column(String(32))  # "rule_filter" | "classifier" | "sensitivity_high"
    reason: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ErrorRecord(Base):
    """One row per failure during the pipeline. Powers error-rate alerting."""
    __tablename__ = "error_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    stage: Mapped[str] = mapped_column(String(64))  # "list" | "fetch" | "classify" | "draft" | "render" | "create_draft"
    error_type: Mapped[str] = mapped_column(String(128))
    error_message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

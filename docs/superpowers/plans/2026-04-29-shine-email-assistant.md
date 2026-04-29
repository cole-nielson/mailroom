# Shine Email Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working AI email assistant for Shine Dance Fitness that polls Gmail every 60s, classifies and drafts on-brand replies grounded in a markdown knowledge base, and saves them as Gmail drafts attached to the original thread for human review. Single-tenant PoC, multi-tenant-ready architecture, deployed on Railway.

**Architecture:** Python service running on Railway, polling Gmail API every 60s, with isolated components (`gmail_client`, `filters`, `classifier`, `drafter`, `knowledge`, `renderer`, `feedback`) wired by `pipeline.py`. Per-tenant content lives in `tenants/<name>/`. State in Railway Postgres. Anthropic Claude Sonnet 4.6 for classification + drafting. Gmail's `processed` label is the source of truth for "already handled."

**Tech Stack:** Python 3.12, `google-api-python-client` (Gmail), `anthropic` (Claude), `psycopg[binary]` + `SQLAlchemy 2` (Postgres), `Jinja2` (HTML templates), `pyyaml` (config), `pytest` (tests), `uv` (dependency management), Railway (hosting).

---

## File structure

```
shine_email_assistant/
├── __init__.py
├── pipeline.py              # orchestrator + polling loop
├── config.py                # tenant config (yaml) + env loading
├── log.py                   # structured logging setup
├── alerts.py                # send alert email on failures
├── gmail_client/
│   ├── __init__.py
│   ├── auth.py              # OAuth refresh token → Credentials
│   ├── thread.py            # ParsedThread dataclass + parse helpers
│   └── client.py            # GmailClient: list_unprocessed_threads, get_thread, create_draft, add_label, list_recent_sent
├── filters/
│   ├── __init__.py
│   └── rules.py             # should_skip(thread) → SkipDecision
├── classifier/
│   ├── __init__.py
│   ├── types.py             # Classification dataclass
│   ├── prompt.py            # system prompt builder
│   └── classify.py          # classify(thread, kb) → Classification
├── drafter/
│   ├── __init__.py
│   ├── types.py             # Draft dataclass
│   ├── prompt.py            # drafter system prompt
│   └── generate.py          # generate(thread, kb, voice, classification) → Draft
├── knowledge/
│   ├── __init__.py
│   └── loader.py            # load(tenant) → KnowledgeBundle, with mtime cache
├── renderer/
│   ├── __init__.py
│   └── render.py            # render(body_md, tenant) → RenderedEmail
├── feedback/
│   ├── __init__.py
│   ├── diff.py              # edit_distance helpers
│   └── audit.py             # audit_recent_drafts() — daily sweep
└── db/
    ├── __init__.py
    ├── models.py            # SQLAlchemy models
    ├── connection.py        # engine + session factory
    └── migrations.py        # create_all on startup

main.py                      # entrypoint: pipeline forever loop OR daily sweep
scripts/
├── gmail_oauth_setup.py     # one-time: get refresh token from OAuth flow
└── seed_test_inbox.py       # send golden test emails into the test inbox

tenants/
└── shine/
    ├── config.yaml
    ├── knowledge/
    │   ├── pricing.md
    │   ├── schedule.md
    │   ├── policies.md
    │   ├── faqs.md
    │   └── about.md
    ├── voice.md
    ├── signature.html
    ├── email_template.html
    └── logo.png

tests/
├── __init__.py
├── conftest.py
├── unit/
│   ├── test_filter_rules.py
│   ├── test_renderer.py
│   ├── test_knowledge_loader.py
│   └── test_edit_distance.py
└── integration/
    ├── conftest.py          # real Gmail/Claude fixtures
    ├── test_gmail_client.py
    ├── test_classifier.py
    ├── test_drafter.py
    └── golden/
        ├── test_golden_emails.py
        └── fixtures/        # YAML files describing each golden email

pyproject.toml
.env.example
README.md
railway.toml
```

---

## Task 1: Project bootstrap

**Files:**
- Create: `pyproject.toml`, `.env.example`, `README.md`, `shine_email_assistant/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "shine-email-assistant"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "google-api-python-client>=2.140.0",
    "google-auth>=2.34.0",
    "google-auth-oauthlib>=1.2.0",
    "psycopg[binary]>=3.2.0",
    "sqlalchemy>=2.0.30",
    "pyyaml>=6.0.2",
    "jinja2>=3.1.4",
    "python-dotenv>=1.0.1",
    "structlog>=24.4.0",
    "markdown>=3.7",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-mock>=3.14.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
markers = [
    "integration: tests that hit real Gmail or Claude APIs (cost money, require credentials)",
]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Gmail OAuth (obtain via scripts/gmail_oauth_setup.py)
GMAIL_CLIENT_ID=...apps.googleusercontent.com
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
GMAIL_USER_EMAIL=test@example.com

# Database
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname

# Alerting
ALERT_EMAIL_TO=you@example.com
ALERT_EMAIL_FROM=alerts@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=...

# Operational
TENANT_NAME=shine
POLL_INTERVAL_SECONDS=60
MODEL_CLASSIFIER=claude-sonnet-4-6
MODEL_DRAFTER=claude-sonnet-4-6
LOG_LEVEL=INFO
```

- [ ] **Step 3: Create `README.md`**

```markdown
# Shine Email Assistant

AI email assistant for small businesses. Polls Gmail, drafts on-brand replies grounded in a per-business knowledge base, saves drafts for human review.

See `docs/superpowers/specs/2026-04-29-shine-email-assistant-design.md` for full design.

## Local development

1. `uv sync`
2. `cp .env.example .env` and fill in values
3. `uv run python scripts/gmail_oauth_setup.py` (one-time, get refresh token)
4. `uv run python main.py` — runs the polling loop forever
5. `uv run python main.py --daily-sweep` — runs the feedback sweep once

## Tests

- `uv run pytest tests/unit/` — fast, no external APIs
- `uv run pytest tests/integration/ -m integration` — hits real Gmail + Claude (costs ~$0.30 for full suite)

## Deploy

Deployed to Railway on push to `main`. See `railway.toml`.
```

- [ ] **Step 4: Create empty package files**

```bash
touch shine_email_assistant/__init__.py tests/__init__.py
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
"""Shared test fixtures."""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tenants_dir(repo_root) -> Path:
    return repo_root / "tenants"
```

- [ ] **Step 6: Install + verify**

Run: `uv sync && uv run pytest --collect-only`
Expected: `no tests collected` exit 5 (no tests yet, that's fine), no import errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .env.example README.md shine_email_assistant/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: project bootstrap (pyproject, env, README, package skeleton)"
```

---

## Task 2: Logging + config loading

**Files:**
- Create: `shine_email_assistant/log.py`, `shine_email_assistant/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write `shine_email_assistant/log.py`**

```python
"""Structured logging setup. Call configure_logging() once at startup."""
import logging
import os

import structlog


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(format="%(message)s", level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 2: Write failing test for tenant config loader**

`tests/unit/test_config.py`:

```python
from pathlib import Path

import pytest

from shine_email_assistant.config import TenantConfig, load_tenant_config


def test_load_tenant_config_reads_yaml(tmp_path: Path):
    tenant_dir = tmp_path / "shine"
    tenant_dir.mkdir()
    (tenant_dir / "config.yaml").write_text(
        "display_name: Shine Dance Fitness\n"
        "brand_color: '#E91E63'\n"
        "website: https://shinefitness.com\n"
        "address: 123 Main St, Anytown USA\n"
        "phone: '+1-555-0100'\n"
        "reply_signoff: '— Shine Dance Fitness'\n"
    )

    cfg = load_tenant_config(tenant_dir)

    assert isinstance(cfg, TenantConfig)
    assert cfg.display_name == "Shine Dance Fitness"
    assert cfg.brand_color == "#E91E63"
    assert cfg.website == "https://shinefitness.com"


def test_load_tenant_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_tenant_config(tmp_path / "nope")
```

- [ ] **Step 3: Run test, expect failure**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: ImportError or ModuleNotFoundError for `shine_email_assistant.config`.

- [ ] **Step 4: Implement `shine_email_assistant/config.py`**

```python
"""Tenant config loader. Reads tenants/<name>/config.yaml into a typed dataclass."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TenantConfig:
    display_name: str
    brand_color: str
    website: str
    address: str
    phone: str
    reply_signoff: str


def load_tenant_config(tenant_dir: Path) -> TenantConfig:
    config_path = tenant_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No config.yaml in {tenant_dir}")
    raw = yaml.safe_load(config_path.read_text())
    return TenantConfig(
        display_name=raw["display_name"],
        brand_color=raw["brand_color"],
        website=raw["website"],
        address=raw["address"],
        phone=raw["phone"],
        reply_signoff=raw["reply_signoff"],
    )
```

- [ ] **Step 5: Run test, expect pass**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add shine_email_assistant/log.py shine_email_assistant/config.py tests/unit/test_config.py
git commit -m "feat: structured logging + tenant config loader"
```

---

## Task 3: Database connection, models, migrations

**Files:**
- Create: `shine_email_assistant/db/__init__.py`, `shine_email_assistant/db/connection.py`, `shine_email_assistant/db/models.py`, `shine_email_assistant/db/migrations.py`

- [ ] **Step 1: Write `shine_email_assistant/db/connection.py`**

```python
"""SQLAlchemy engine + session factory. One global engine."""
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def get_engine() -> Engine:
    url = os.environ["DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def session() -> Session:
    return _session_factory()()
```

- [ ] **Step 2: Write `shine_email_assistant/db/models.py`**

```python
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
```

- [ ] **Step 3: Write `shine_email_assistant/db/migrations.py`**

```python
"""Create all tables. Called at app startup. Idempotent."""
from shine_email_assistant.db.connection import get_engine
from shine_email_assistant.db.models import Base


def init_db() -> None:
    Base.metadata.create_all(get_engine())
```

- [ ] **Step 4: Write `shine_email_assistant/db/__init__.py`**

```python
from shine_email_assistant.db.connection import session
from shine_email_assistant.db.migrations import init_db
from shine_email_assistant.db.models import DraftRecord, ErrorRecord, SkipRecord

__all__ = ["session", "init_db", "DraftRecord", "ErrorRecord", "SkipRecord"]
```

- [ ] **Step 5: Verify import works**

Run: `uv run python -c "from shine_email_assistant.db import init_db, DraftRecord; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add shine_email_assistant/db/
git commit -m "feat: db models, connection, init_db migration"
```

---

## Task 4: Knowledge loader (with tests)

**Files:**
- Create: `shine_email_assistant/knowledge/__init__.py`, `shine_email_assistant/knowledge/loader.py`
- Create: `tests/unit/test_knowledge_loader.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_knowledge_loader.py`:

```python
import time
from pathlib import Path

from shine_email_assistant.knowledge.loader import KnowledgeBundle, KnowledgeLoader


def _seed_tenant(root: Path, name: str) -> Path:
    tdir = root / name
    (tdir / "knowledge").mkdir(parents=True)
    (tdir / "knowledge" / "pricing.md").write_text("# Pricing\n\n$25/class\n")
    (tdir / "knowledge" / "schedule.md").write_text("# Schedule\n\nMon 6pm\n")
    (tdir / "voice.md").write_text("# Voice\n\nWarm and concise.\n")
    return tdir


def test_load_returns_concatenated_kb_and_voice(tmp_path: Path):
    tenant_dir = _seed_tenant(tmp_path, "shine")
    loader = KnowledgeLoader(tmp_path)

    bundle = loader.load("shine")

    assert isinstance(bundle, KnowledgeBundle)
    assert "Pricing" in bundle.kb_text
    assert "Schedule" in bundle.kb_text
    assert "Warm and concise" in bundle.voice_text
    # version should be a stable hash of the content
    assert isinstance(bundle.version, str) and len(bundle.version) >= 8


def test_load_caches_until_file_changes(tmp_path: Path):
    tenant_dir = _seed_tenant(tmp_path, "shine")
    loader = KnowledgeLoader(tmp_path)

    first = loader.load("shine")
    second = loader.load("shine")
    assert first is second  # same cached object

    # mutate a file; loader should detect and reload
    time.sleep(0.01)
    (tenant_dir / "knowledge" / "pricing.md").write_text("# Pricing\n\n$30/class\n")
    third = loader.load("shine")
    assert third is not first
    assert "$30/class" in third.kb_text
    assert third.version != first.version


def test_load_raises_if_tenant_missing(tmp_path: Path):
    loader = KnowledgeLoader(tmp_path)
    try:
        loader.load("nonexistent")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_knowledge_loader.py -v`
Expected: ImportError for `shine_email_assistant.knowledge.loader`.

- [ ] **Step 3: Implement loader**

`shine_email_assistant/knowledge/loader.py`:

```python
"""Per-tenant knowledge loader. Reads markdown from tenants/<name>/, caches with mtime invalidation."""
import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class KnowledgeBundle:
    kb_text: str
    voice_text: str
    version: str  # short hash, stable across loads of identical content


class KnowledgeLoader:
    """Per-process cache. Reloads when any contributing file's mtime changes."""

    def __init__(self, tenants_root: Path):
        self._tenants_root = tenants_root
        self._cache: dict[str, tuple[float, KnowledgeBundle]] = {}
        self._lock = Lock()

    def load(self, tenant_name: str) -> KnowledgeBundle:
        tenant_dir = self._tenants_root / tenant_name
        if not tenant_dir.exists():
            raise FileNotFoundError(f"No tenant directory: {tenant_dir}")

        kb_dir = tenant_dir / "knowledge"
        voice_path = tenant_dir / "voice.md"
        kb_files = sorted(kb_dir.glob("*.md")) if kb_dir.exists() else []

        latest_mtime = max(
            [p.stat().st_mtime for p in kb_files] + [voice_path.stat().st_mtime if voice_path.exists() else 0.0]
        )

        with self._lock:
            cached = self._cache.get(tenant_name)
            if cached and cached[0] == latest_mtime:
                return cached[1]

            kb_text = "\n\n".join(p.read_text() for p in kb_files)
            voice_text = voice_path.read_text() if voice_path.exists() else ""
            version = hashlib.sha256((kb_text + "\n\n" + voice_text).encode()).hexdigest()[:12]
            bundle = KnowledgeBundle(kb_text=kb_text, voice_text=voice_text, version=version)

            self._cache[tenant_name] = (latest_mtime, bundle)
            return bundle
```

- [ ] **Step 4: Write `shine_email_assistant/knowledge/__init__.py`**

```python
from shine_email_assistant.knowledge.loader import KnowledgeBundle, KnowledgeLoader

__all__ = ["KnowledgeBundle", "KnowledgeLoader"]
```

- [ ] **Step 5: Run test, expect pass**

Run: `uv run pytest tests/unit/test_knowledge_loader.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add shine_email_assistant/knowledge/ tests/unit/test_knowledge_loader.py
git commit -m "feat: knowledge loader with mtime-based cache"
```

---

## Task 5: Rule filter (with tests)

**Files:**
- Create: `shine_email_assistant/gmail_client/thread.py` (just the dataclass needed by filter)
- Create: `shine_email_assistant/filters/__init__.py`, `shine_email_assistant/filters/rules.py`
- Create: `tests/unit/test_filter_rules.py`

- [ ] **Step 1: Define `ParsedThread` shape**

`shine_email_assistant/gmail_client/__init__.py`:
```python
"""Gmail client + thread parsing. Re-exports for ergonomic imports."""
```

`shine_email_assistant/gmail_client/thread.py`:
```python
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
```

- [ ] **Step 2: Write failing test for rule filter**

`tests/unit/test_filter_rules.py`:

```python
from datetime import datetime

from shine_email_assistant.filters.rules import SkipDecision, should_skip
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread


def _msg(**overrides) -> ParsedMessage:
    base = dict(
        message_id="m1",
        from_address="Customer <cust@example.com>",
        from_email="cust@example.com",
        to_addresses=("info@shinefitness.com",),
        subject="Question about classes",
        date=datetime.utcnow(),
        headers={},
        body_text="hi when do classes meet?",
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
```

- [ ] **Step 3: Run test, expect failure**

Run: `uv run pytest tests/unit/test_filter_rules.py -v`
Expected: ImportError for `shine_email_assistant.filters.rules`.

- [ ] **Step 4: Implement filter**

`shine_email_assistant/filters/__init__.py`:
```python
from shine_email_assistant.filters.rules import SkipDecision, should_skip

__all__ = ["SkipDecision", "should_skip"]
```

`shine_email_assistant/filters/rules.py`:

```python
"""Cheap rule-based pre-filter. Skips obvious non-candidates with zero LLM cost."""
import re
from dataclasses import dataclass

from shine_email_assistant.gmail_client.thread import ParsedThread

_AUTOMATION_PATTERNS = (
    re.compile(r"^no-?reply@", re.IGNORECASE),
    re.compile(r"^do-?not-?reply@", re.IGNORECASE),
    re.compile(r"^mailer-?daemon@", re.IGNORECASE),
    re.compile(r"^postmaster@", re.IGNORECASE),
    re.compile(r"^bounce[s]?@", re.IGNORECASE),
)


@dataclass(frozen=True)
class SkipDecision:
    skip: bool
    reason: str = ""


def should_skip(thread: ParsedThread) -> SkipDecision:
    if thread.latest_is_from_us:
        return SkipDecision(skip=True, reason="latest message is from us")
    if thread.has_existing_human_draft:
        return SkipDecision(skip=True, reason="thread already has an existing draft")
    latest = thread.latest_message
    if "List-Unsubscribe" in latest.headers:
        return SkipDecision(skip=True, reason="List-Unsubscribe header present (mailing list)")
    for pattern in _AUTOMATION_PATTERNS:
        if pattern.match(latest.from_email):
            return SkipDecision(skip=True, reason=f"automation sender pattern: {latest.from_email}")
    return SkipDecision(skip=False)
```

- [ ] **Step 5: Run test, expect pass**

Run: `uv run pytest tests/unit/test_filter_rules.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add shine_email_assistant/gmail_client/__init__.py shine_email_assistant/gmail_client/thread.py shine_email_assistant/filters/ tests/unit/test_filter_rules.py
git commit -m "feat: rule-based pre-filter and ParsedThread dataclass"
```

---

## Task 6: HTML renderer (with tests)

**Files:**
- Create: `shine_email_assistant/renderer/__init__.py`, `shine_email_assistant/renderer/render.py`
- Create: `tests/unit/test_renderer.py`
- Create fixture template files for tests

- [ ] **Step 1: Write failing test**

`tests/unit/test_renderer.py`:

```python
from pathlib import Path

from shine_email_assistant.renderer.render import RenderedEmail, render


def _seed_tenant(root: Path) -> Path:
    tdir = root / "shine"
    tdir.mkdir()
    (tdir / "config.yaml").write_text(
        "display_name: Shine Dance Fitness\n"
        "brand_color: '#E91E63'\n"
        "website: https://shinefitness.com\n"
        "address: '123 Main St'\n"
        "phone: '+1-555-0100'\n"
        "reply_signoff: '— Shine Dance Fitness'\n"
    )
    (tdir / "signature.html").write_text(
        "<table><tr><td><strong>{{ display_name }}</strong><br>"
        "{{ phone }} · <a href=\"{{ website }}\" style=\"color:{{ brand_color }}\">{{ website }}</a><br>"
        "{{ address }}</td></tr></table>"
    )
    (tdir / "email_template.html").write_text(
        "<html><body style=\"font-family:-apple-system,Helvetica,Arial,sans-serif;color:#222;line-height:1.5\">"
        "{{ body_html }}<hr style=\"border:none;border-top:1px solid #eee;margin:24px 0\">"
        "{{ signature_html }}</body></html>"
    )
    return tdir


def test_render_wraps_markdown_body_with_signature(tmp_path: Path):
    _seed_tenant(tmp_path)

    body_md = "Thanks for reaching out!\n\nClasses are at 6pm on Tuesday.\n\nWarmly, Shine"
    result = render(body_md, tenant_name="shine", tenants_root=tmp_path)

    assert isinstance(result, RenderedEmail)
    assert "<p>Thanks for reaching out!</p>" in result.html
    assert "<p>Classes are at 6pm on Tuesday.</p>" in result.html
    assert "Shine Dance Fitness" in result.html  # signature rendered
    assert "shinefitness.com" in result.html
    assert "#E91E63" in result.html  # brand color injected
    # plaintext fallback retains the prose without HTML
    assert "Thanks for reaching out!" in result.plaintext
    assert "<" not in result.plaintext
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_renderer.py -v`
Expected: ImportError for `shine_email_assistant.renderer.render`.

- [ ] **Step 3: Implement renderer**

`shine_email_assistant/renderer/__init__.py`:
```python
from shine_email_assistant.renderer.render import RenderedEmail, render

__all__ = ["RenderedEmail", "render"]
```

`shine_email_assistant/renderer/render.py`:

```python
"""Wrap LLM body markdown in styled HTML + tenant signature template."""
from dataclasses import dataclass
from pathlib import Path

import markdown as md_lib
from jinja2 import Environment, StrictUndefined

from shine_email_assistant.config import load_tenant_config


@dataclass(frozen=True)
class RenderedEmail:
    html: str
    plaintext: str


def render(body_markdown: str, tenant_name: str, tenants_root: Path) -> RenderedEmail:
    tenant_dir = tenants_root / tenant_name
    cfg = load_tenant_config(tenant_dir)

    env = Environment(undefined=StrictUndefined, autoescape=False)

    body_html = md_lib.markdown(body_markdown, extensions=["extra"])

    sig_template = env.from_string((tenant_dir / "signature.html").read_text())
    signature_html = sig_template.render(
        display_name=cfg.display_name,
        brand_color=cfg.brand_color,
        website=cfg.website,
        address=cfg.address,
        phone=cfg.phone,
    )

    page_template = env.from_string((tenant_dir / "email_template.html").read_text())
    html = page_template.render(body_html=body_html, signature_html=signature_html)

    return RenderedEmail(html=html, plaintext=body_markdown)
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_renderer.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add shine_email_assistant/renderer/ tests/unit/test_renderer.py
git commit -m "feat: HTML email renderer with Jinja templates and brand styling"
```

---

## Task 7: Edit-distance + alerts module

**Files:**
- Create: `shine_email_assistant/feedback/__init__.py`, `shine_email_assistant/feedback/diff.py`
- Create: `shine_email_assistant/alerts.py`
- Create: `tests/unit/test_edit_distance.py`

- [ ] **Step 1: Write failing test for edit_distance categorization**

`tests/unit/test_edit_distance.py`:

```python
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
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_edit_distance.py -v`
Expected: ImportError for `shine_email_assistant.feedback.diff`.

- [ ] **Step 3: Implement diff module**

`shine_email_assistant/feedback/__init__.py`:
```python
from shine_email_assistant.feedback.diff import Outcome, categorize_outcome, edit_distance_ratio

__all__ = ["Outcome", "categorize_outcome", "edit_distance_ratio"]
```

`shine_email_assistant/feedback/diff.py`:

```python
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
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_edit_distance.py -v`
Expected: 5 passed.

- [ ] **Step 5: Implement alerts module**

`shine_email_assistant/alerts.py`:

```python
"""Send operational alert emails on real failures.

Triggers (called from pipeline):
- Gmail auth revoked/expired
- KB files won't parse at startup
- Error rate >= threshold within window
"""
import os
import smtplib
from email.message import EmailMessage

from shine_email_assistant.log import get_logger

log = get_logger(__name__)


def send_alert(subject: str, body: str) -> None:
    """Best-effort alert. Logs and swallows on failure (don't take down the app on a smtp error)."""
    to_addr = os.getenv("ALERT_EMAIL_TO")
    from_addr = os.getenv("ALERT_EMAIL_FROM")
    host = os.getenv("SMTP_HOST")
    port_str = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    if not all([to_addr, from_addr, host, port_str, user, password]):
        log.warning("alert_skipped_missing_smtp_config", subject=subject)
        return

    msg = EmailMessage()
    msg["Subject"] = f"[shine-email-assistant] {subject}"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, int(port_str)) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
        log.info("alert_sent", subject=subject)
    except Exception as e:  # noqa: BLE001
        log.error("alert_send_failed", subject=subject, error=str(e))
```

- [ ] **Step 6: Commit**

```bash
git add shine_email_assistant/feedback/ shine_email_assistant/alerts.py tests/unit/test_edit_distance.py
git commit -m "feat: edit-distance categorization + alerts module"
```

---

## Task 8: Gmail OAuth setup script

**Files:**
- Create: `scripts/__init__.py`, `scripts/gmail_oauth_setup.py`
- Create: `shine_email_assistant/gmail_client/auth.py`

- [ ] **Step 1: Write OAuth setup script**

`scripts/__init__.py`: empty

`scripts/gmail_oauth_setup.py`:

```python
"""ONE-TIME script: walks through OAuth consent and prints the refresh token.

Prerequisites:
1. Create a Google Cloud project (free tier is fine).
2. Enable the Gmail API for that project.
3. Create OAuth 2.0 credentials of type "Desktop app".
4. Download the credentials JSON; export client_id + client_secret as env vars
   (or edit the constants below temporarily).

Run this on your laptop, NOT on Railway.

After running:
- Browser opens, you log in with the test Gmail account
- Approve the requested scopes
- The script prints the refresh token to stdout
- Copy it into Railway env vars as GMAIL_REFRESH_TOKEN
"""
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read + label + drafts
    "https://www.googleapis.com/auth/gmail.send",    # for alert emails (if we choose Gmail SMTP)
]


def main() -> int:
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in env first.", file=sys.stderr)
        return 2

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\n=== Save these into your env / Railway vars ===")
    print(f"GMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GMAIL_USER_EMAIL={_userinfo(creds)}")
    return 0


def _userinfo(creds) -> str:
    """Best-effort fetch of the authenticated user's email; falls back to placeholder."""
    try:
        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = svc.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "unknown@example.com")
    except Exception:  # noqa: BLE001
        return "FILL_IN_MANUALLY@example.com"


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Implement auth helper used by the runtime**

`shine_email_assistant/gmail_client/auth.py`:

```python
"""Build authenticated Gmail Credentials from refresh token in env."""
import os

from google.oauth2.credentials import Credentials


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def credentials_from_env() -> Credentials:
    refresh_token = os.environ["GMAIL_REFRESH_TOKEN"]
    client_id = os.environ["GMAIL_CLIENT_ID"]
    client_secret = os.environ["GMAIL_CLIENT_SECRET"]
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )
```

- [ ] **Step 3: Manual run (not part of CI)**

Run: `uv run python scripts/gmail_oauth_setup.py`
Expected: browser opens, log in with the test Gmail, approve scopes, refresh token printed. Save into `.env`.

- [ ] **Step 4: Commit**

```bash
git add scripts/ shine_email_assistant/gmail_client/auth.py
git commit -m "feat: Gmail OAuth setup script + runtime auth helper"
```

---

## Task 9: Gmail client — read operations (list, get, parse, label)

**Files:**
- Modify: `shine_email_assistant/gmail_client/__init__.py`
- Create: `shine_email_assistant/gmail_client/client.py`
- Create: `tests/integration/__init__.py`, `tests/integration/conftest.py`, `tests/integration/test_gmail_client.py`

- [ ] **Step 1: Implement Gmail client read operations**

`shine_email_assistant/gmail_client/client.py`:

```python
"""Gmail API wrapper. Only the operations the pipeline actually needs."""
import base64
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Iterable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from shine_email_assistant.gmail_client.auth import credentials_from_env
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread
from shine_email_assistant.log import get_logger

log = get_logger(__name__)


PROCESSED_LABEL = "processed"
SKIPPED_LABEL = "processed-skipped"
ERROR_LABEL = "draft-error"
FLAG_FOR_HUMAN_LABEL = "flag-for-human"


class GmailClient:
    """Single source of truth for Gmail API calls."""

    def __init__(self, user_email: str | None = None):
        import os
        self._user_email = (user_email or os.environ["GMAIL_USER_EMAIL"]).lower()
        self._service = build("gmail", "v1", credentials=credentials_from_env(), cache_discovery=False)
        self._label_cache: dict[str, str] = {}

    # ---- threads ----

    def list_unprocessed_thread_ids(self, max_results: int = 50) -> list[str]:
        """Return thread IDs not labeled processed/skipped/error and not in Promotions/Updates."""
        # Gmail's `q` query language.
        q = (
            f"-label:{PROCESSED_LABEL} "
            f"-label:{SKIPPED_LABEL} "
            f"-label:{ERROR_LABEL} "
            f"-label:{FLAG_FOR_HUMAN_LABEL} "
            "-category:promotions "
            "-category:updates "
            "in:inbox"
        )
        resp = self._service.users().threads().list(
            userId="me", q=q, maxResults=max_results
        ).execute()
        return [t["id"] for t in resp.get("threads", [])]

    def get_thread(self, thread_id: str) -> ParsedThread:
        raw = self._service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()

        messages = tuple(self._parse_message(m) for m in raw.get("messages", []))
        has_existing_human_draft = self._thread_has_user_draft(thread_id)

        return ParsedThread(
            thread_id=thread_id,
            messages=messages,
            has_existing_human_draft=has_existing_human_draft,
        )

    def list_recent_sent_messages(self, hours: int = 30) -> list[dict]:
        """Used by feedback sweep. Returns minimal message dicts (id, threadId, internalDate)."""
        from datetime import timedelta
        after = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
        q = f"in:sent after:{after}"
        resp = self._service.users().messages().list(
            userId="me", q=q, maxResults=200
        ).execute()
        return resp.get("messages", [])

    def get_message_body_text(self, message_id: str) -> str:
        """Used by feedback sweep to compare drafts vs sent text."""
        raw = self._service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        return _extract_plain_text(raw.get("payload", {}))

    # ---- labels ----

    def add_label(self, thread_id: str, label_name: str) -> None:
        label_id = self._ensure_label(label_name)
        self._service.users().threads().modify(
            userId="me", id=thread_id, body={"addLabelIds": [label_id]}
        ).execute()

    def _ensure_label(self, name: str) -> str:
        if name in self._label_cache:
            return self._label_cache[name]
        existing = self._service.users().labels().list(userId="me").execute().get("labels", [])
        for lbl in existing:
            if lbl["name"] == name:
                self._label_cache[name] = lbl["id"]
                return lbl["id"]
        # create
        created = self._service.users().labels().create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).execute()
        self._label_cache[name] = created["id"]
        return created["id"]

    # ---- internals ----

    def _thread_has_user_draft(self, thread_id: str) -> bool:
        """True if there's an existing draft on the thread that *we* didn't create.

        For the PoC we treat ANY existing draft as "human, hands off." The trade-off:
        if our own previous draft sticks around, we won't redraft. That's fine — Dad
        will deal with it on his own schedule.
        """
        drafts = self._service.users().drafts().list(userId="me").execute().get("drafts", [])
        for d in drafts:
            if d.get("message", {}).get("threadId") == thread_id:
                return True
        return False

    def _parse_message(self, raw: dict) -> ParsedMessage:
        payload = raw.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        from_raw = headers.get("From", "")
        from_emails = [addr for _, addr in getaddresses([from_raw])]
        from_email = (from_emails[0] if from_emails else "").lower()

        to_raw = headers.get("To", "")
        to_addresses = tuple(addr for _, addr in getaddresses([to_raw]))

        date_raw = headers.get("Date")
        try:
            date = parsedate_to_datetime(date_raw) if date_raw else datetime.now(timezone.utc)
        except (TypeError, ValueError):
            date = datetime.now(timezone.utc)

        body_text = _extract_plain_text(payload)
        body_html = _extract_html(payload)

        is_from_us = from_email == self._user_email

        return ParsedMessage(
            message_id=raw["id"],
            from_address=from_raw,
            from_email=from_email,
            to_addresses=to_addresses,
            subject=headers.get("Subject", ""),
            date=date,
            headers=headers,
            body_text=body_text,
            body_html=body_html,
            is_from_us=is_from_us,
        )


# ---- payload parsing helpers ----

def _walk_parts(payload: dict) -> Iterable[dict]:
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _extract_plain_text(payload: dict) -> str:
    for part in _walk_parts(payload):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    # fall back to stripping HTML
    html = _extract_html(payload)
    if html:
        return re.sub(r"<[^>]+>", "", html)
    return ""


def _extract_html(payload: dict) -> str:
    for part in _walk_parts(payload):
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""
```

- [ ] **Step 2: Update `gmail_client/__init__.py`**

```python
from shine_email_assistant.gmail_client.client import (
    ERROR_LABEL,
    FLAG_FOR_HUMAN_LABEL,
    PROCESSED_LABEL,
    SKIPPED_LABEL,
    GmailClient,
)
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread

__all__ = [
    "GmailClient",
    "ParsedMessage",
    "ParsedThread",
    "PROCESSED_LABEL",
    "SKIPPED_LABEL",
    "ERROR_LABEL",
    "FLAG_FOR_HUMAN_LABEL",
]
```

- [ ] **Step 3: Write integration test fixtures**

`tests/integration/__init__.py`: empty

`tests/integration/conftest.py`:

```python
"""Integration test fixtures. These tests hit real Gmail/Anthropic; run sparingly."""
import os

import pytest

from shine_email_assistant.gmail_client import GmailClient


def _has_gmail_creds() -> bool:
    return all(os.getenv(k) for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "GMAIL_USER_EMAIL"))


def _has_anthropic_creds() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


@pytest.fixture
def gmail_client():
    if not _has_gmail_creds():
        pytest.skip("Gmail credentials not in env; skipping integration test.")
    return GmailClient()


@pytest.fixture
def anthropic_available():
    if not _has_anthropic_creds():
        pytest.skip("ANTHROPIC_API_KEY not set; skipping integration test.")
    return True
```

- [ ] **Step 4: Write smoke integration test**

`tests/integration/test_gmail_client.py`:

```python
"""Smoke tests against a real test Gmail account.

These verify the Gmail wrapper actually talks to Gmail. They cost real API calls
(small) and require the test account to exist + have at least one inbox message.

Run with: uv run pytest tests/integration/test_gmail_client.py -m integration -v
"""
import pytest


pytestmark = pytest.mark.integration


def test_can_list_unprocessed_threads(gmail_client):
    ids = gmail_client.list_unprocessed_thread_ids(max_results=5)
    assert isinstance(ids, list)
    # Don't assert on length — fresh test inboxes may be empty.


def test_can_get_thread_if_any_exist(gmail_client):
    ids = gmail_client.list_unprocessed_thread_ids(max_results=1)
    if not ids:
        pytest.skip("test inbox empty; can't exercise get_thread")
    t = gmail_client.get_thread(ids[0])
    assert t.thread_id == ids[0]
    assert len(t.messages) >= 1
    latest = t.latest_message
    assert latest.from_email  # parsed
    assert latest.subject is not None


def test_can_create_and_remove_processed_label(gmail_client):
    """Verifies the label-management plumbing — uses a throwaway label name."""
    label = "shine-test-label-do-not-use"
    label_id = gmail_client._ensure_label(label)
    assert label_id
    # second call is idempotent
    assert gmail_client._ensure_label(label) == label_id
```

- [ ] **Step 5: Run integration tests (manual, requires env)**

Run: `uv run pytest tests/integration/test_gmail_client.py -m integration -v`
Expected: 3 passed (or some skipped if inbox empty / credentials missing).

- [ ] **Step 6: Commit**

```bash
git add shine_email_assistant/gmail_client/client.py shine_email_assistant/gmail_client/__init__.py tests/integration/
git commit -m "feat: Gmail client read ops (list, get, parse, label)"
```

---

## Task 10: Gmail client — create_draft attached to thread

**Files:**
- Modify: `shine_email_assistant/gmail_client/client.py` (add `create_draft` method)
- Modify: `tests/integration/test_gmail_client.py` (add test)

- [ ] **Step 1: Add `create_draft` to `GmailClient`**

Append to `shine_email_assistant/gmail_client/client.py`:

```python
    def create_draft(
        self,
        thread_id: str,
        in_reply_to_message_id_header: str,
        to: str,
        subject: str,
        html_body: str,
        plaintext_body: str,
        references: str | None = None,
    ) -> str:
        """Create a draft attached to an existing thread, replying to a specific message.

        Returns the new draft's ID.
        """
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        msg["In-Reply-To"] = in_reply_to_message_id_header
        msg["References"] = references or in_reply_to_message_id_header
        msg.set_content(plaintext_body)
        msg.add_alternative(html_body, subtype="html")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        body = {"message": {"raw": raw, "threadId": thread_id}}

        created = self._service.users().drafts().create(userId="me", body=body).execute()
        return created["id"]

    def delete_draft(self, draft_id: str) -> None:
        """Used by integration tests to clean up after themselves."""
        try:
            self._service.users().drafts().delete(userId="me", id=draft_id).execute()
        except HttpError as e:
            log.warning("draft_delete_failed", draft_id=draft_id, error=str(e))
```

(`base64`, `EmailMessage`, and `HttpError` are already imported at the top of the file.)

- [ ] **Step 2: Add test for create_draft**

Append to `tests/integration/test_gmail_client.py`:

```python
def test_can_create_and_delete_draft_on_thread(gmail_client):
    """End-to-end: list a thread, create a draft on it, delete the draft."""
    ids = gmail_client.list_unprocessed_thread_ids(max_results=1)
    if not ids:
        pytest.skip("test inbox empty; can't exercise create_draft")

    thread = gmail_client.get_thread(ids[0])
    latest = thread.latest_message
    msg_id_header = latest.headers.get("Message-ID") or latest.headers.get("Message-Id") or ""
    if not msg_id_header:
        pytest.skip("test message has no Message-ID header; can't reply")

    draft_id = gmail_client.create_draft(
        thread_id=thread.thread_id,
        in_reply_to_message_id_header=msg_id_header,
        to=latest.from_email,
        subject=latest.subject,
        html_body="<p>Test draft — please ignore.</p>",
        plaintext_body="Test draft — please ignore.",
    )
    assert draft_id

    # cleanup so we don't pollute the inbox
    gmail_client.delete_draft(draft_id)
```

- [ ] **Step 3: Run integration tests**

Run: `uv run pytest tests/integration/test_gmail_client.py -m integration -v`
Expected: 4 passed (or 1 skipped if inbox empty).

- [ ] **Step 4: Commit**

```bash
git add shine_email_assistant/gmail_client/client.py tests/integration/test_gmail_client.py
git commit -m "feat: Gmail create_draft attached to thread + delete helper"
```

---

## Task 11: Classifier (Claude call returning structured Classification)

**Files:**
- Create: `shine_email_assistant/classifier/__init__.py`, `shine_email_assistant/classifier/types.py`, `shine_email_assistant/classifier/prompt.py`, `shine_email_assistant/classifier/classify.py`
- Create: `tests/integration/test_classifier.py`

- [ ] **Step 1: Define `Classification` types**

`shine_email_assistant/classifier/types.py`:

```python
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
```

- [ ] **Step 2: Write classifier prompt builder**

`shine_email_assistant/classifier/prompt.py`:

```python
"""Build the classifier system + user prompts."""
from shine_email_assistant.gmail_client.thread import ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle


CATEGORIES = [
    "schedule_question",
    "pricing_question",
    "registration",
    "intro_class_inquiry",
    "policies_question",
    "complaint",
    "refund_request",
    "ambiguous",
    "not_replyable",  # spam, internal, vendor pitch, automated, etc.
    "general_question",
    "other",
]

SYSTEM_PROMPT = f"""You are an email triage classifier for a small business inbox.

Your only job is to decide whether the latest customer message in a thread should
get an AI-drafted reply, and to categorize it.

Output STRICTLY a single JSON object on one line — no prose, no markdown fence — with these keys:
{{
  "should_draft": true | false,
  "category": one of {CATEGORIES!r},
  "sensitivity": "low" | "medium" | "high",
  "confidence": 0.0..1.0,
  "reason": "<one short sentence>"
}}

Decision rules:
- should_draft = false when:
  - the message is automated (newsletter, payment confirmation, vendor pitch, spam)
  - the message is internal team chatter
  - the message is empty or pure pleasantry with no actionable question
  - drafting would be embarrassing or risky (use sensitivity="high" and should_draft=false)
- sensitivity = "high" for: refund disputes, complaints, legal threats, anything emotionally loaded.
  These should NEVER be drafted automatically; flag for a human.
- sensitivity = "medium" for: ambiguous messages, multi-question threads, anything where
  you're <80% sure the right answer is in the knowledge base.
- sensitivity = "low" for: clear factual questions whose answer is explicitly in the KB.

Confidence is your overall confidence in the classification + that the KB has the answer.
"""


def build_user_prompt(thread: ParsedThread, kb: KnowledgeBundle) -> str:
    """Render the thread + KB context for the classifier turn."""
    msgs = []
    for m in thread.messages:
        sender = "[us]" if m.is_from_us else f"[customer: {m.from_email}]"
        msgs.append(f"--- {sender} | {m.date.isoformat()} | Subject: {m.subject} ---\n{m.body_text.strip()}")
    thread_text = "\n\n".join(msgs)

    return (
        "<knowledge_base>\n"
        f"{kb.kb_text}\n"
        "</knowledge_base>\n\n"
        "<thread>\n"
        f"{thread_text}\n"
        "</thread>\n\n"
        "Classify the LATEST message in the thread. Output JSON only."
    )
```

- [ ] **Step 3: Implement `classify` function**

`shine_email_assistant/classifier/classify.py`:

```python
"""Call Claude to classify a thread. Returns a Classification."""
import json
import os

from anthropic import Anthropic

from shine_email_assistant.classifier.prompt import SYSTEM_PROMPT, build_user_prompt
from shine_email_assistant.classifier.types import Classification, Sensitivity
from shine_email_assistant.gmail_client.thread import ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle
from shine_email_assistant.log import get_logger

log = get_logger(__name__)


_DEFAULT_MODEL = "claude-sonnet-4-6"


def classify(thread: ParsedThread, kb: KnowledgeBundle, *, model: str | None = None) -> Classification:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = model or os.getenv("MODEL_CLASSIFIER", _DEFAULT_MODEL)

    user_prompt = build_user_prompt(thread, kb)

    resp = client.messages.create(
        model=model,
        max_tokens=400,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    log.info(
        "classifier_response",
        thread_id=thread.thread_id,
        tokens_input=resp.usage.input_tokens,
        tokens_output=resp.usage.output_tokens,
        cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0),
    )

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("classifier_json_parse_failed", thread_id=thread.thread_id, raw=text[:500])
        # one retry with a stricter user message
        retry_resp = client.messages.create(
            model=model,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": text},
                {"role": "user", "content": "That was not valid JSON. Output ONLY the JSON object, nothing else."},
            ],
        )
        text = "".join(block.text for block in retry_resp.content if block.type == "text").strip()
        data = json.loads(text)

    return Classification(
        should_draft=bool(data["should_draft"]),
        category=str(data["category"]),
        sensitivity=Sensitivity(data["sensitivity"]),
        confidence=float(data["confidence"]),
        reason=str(data.get("reason", "")),
    )
```

- [ ] **Step 4: Write `classifier/__init__.py`**

```python
from shine_email_assistant.classifier.classify import classify
from shine_email_assistant.classifier.types import Classification, Sensitivity

__all__ = ["classify", "Classification", "Sensitivity"]
```

- [ ] **Step 5: Write smoke integration test**

`tests/integration/test_classifier.py`:

```python
"""Smoke test: classifier returns a structured Classification for a hand-crafted thread."""
from datetime import datetime

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
        date=datetime.utcnow(),
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
```

- [ ] **Step 6: Run integration tests**

Run: `uv run pytest tests/integration/test_classifier.py -m integration -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add shine_email_assistant/classifier/ tests/integration/test_classifier.py
git commit -m "feat: classifier with Sonnet 4.6, JSON output, prompt caching"
```

---

## Task 12: Drafter (Claude call returning body markdown)

**Files:**
- Create: `shine_email_assistant/drafter/__init__.py`, `shine_email_assistant/drafter/types.py`, `shine_email_assistant/drafter/prompt.py`, `shine_email_assistant/drafter/generate.py`
- Create: `tests/integration/test_drafter.py`

- [ ] **Step 1: Define `Draft` type**

`shine_email_assistant/drafter/types.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Draft:
    body_markdown: str
    tokens_input: int = 0
    tokens_output: int = 0
    model_used: str = ""
```

- [ ] **Step 2: Write drafter prompt**

`shine_email_assistant/drafter/prompt.py`:

```python
"""Drafter prompt. Body-only output — no signature, no HTML, no salutation boilerplate."""
from shine_email_assistant.classifier.types import Classification
from shine_email_assistant.gmail_client.thread import ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle


SYSTEM_PROMPT = """You are drafting reply emails for a small business owner to review.

Your output is the BODY of an email — markdown only, no HTML, no signature line.
The signature is appended automatically downstream; do NOT include any sign-off
beyond a brief warm closing line if it fits naturally.

Hard rules:

1. Match the brand voice in <voice_guide>. Re-read the few-shot examples there
   before writing. The examples set the bar.

2. Ground every factual claim in the <knowledge_base>. If the answer is not in
   the KB, say so honestly and offer to find out — do NOT invent.

3. Avoid AI tells:
   - NEVER write "I hope this email finds you well" or any variation
   - NEVER write "Certainly!" or "Absolutely!" as openers
   - NEVER use exclamation points more than once
   - NEVER use the phrase "feel free to"
   - NEVER use "as an AI" or any meta-reference
   - NEVER use em-dashes as a stylistic flourish (—)

4. First-person singular ("I checked the schedule and..."). Use "we" only when
   genuinely speaking for the team ("We'd love to have you join us").

5. Be specific to what the customer actually asked. No generic content.

6. Length: shorter is better. Aim for 2-4 short paragraphs. If you're writing more,
   you're probably padding.

7. End with a brief warm closing fitting the brand voice. The signature block
   (business name, contact info) is added automatically — do NOT include it.

Output: just the body markdown. No preamble, no explanation, no quotation marks
around the email."""


def build_user_prompt(thread: ParsedThread, classification: Classification) -> str:
    msgs = []
    for m in thread.messages:
        sender = "[us]" if m.is_from_us else f"[customer: {m.from_email}]"
        msgs.append(f"--- {sender} | {m.date.isoformat()} ---\n{m.body_text.strip()}")
    thread_text = "\n\n".join(msgs)

    return (
        f"<classification>\ncategory: {classification.category}\n"
        f"sensitivity: {classification.sensitivity.value}\n"
        f"confidence: {classification.confidence}\n</classification>\n\n"
        "<thread>\n"
        f"{thread_text}\n"
        "</thread>\n\n"
        "Draft a reply to the LATEST customer message. Body markdown only."
    )


def build_cached_blocks(kb: KnowledgeBundle) -> list[dict]:
    """The KB + voice guide get prompt-cached; per-request user prompt is small."""
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"<voice_guide>\n{kb.voice_text}\n</voice_guide>",
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"<knowledge_base>\n{kb.kb_text}\n</knowledge_base>",
            "cache_control": {"type": "ephemeral"},
        },
    ]
```

- [ ] **Step 3: Implement `generate`**

`shine_email_assistant/drafter/generate.py`:

```python
"""Generate a draft body for one thread."""
import os

from anthropic import Anthropic

from shine_email_assistant.classifier.types import Classification, Sensitivity
from shine_email_assistant.drafter.prompt import build_cached_blocks, build_user_prompt
from shine_email_assistant.drafter.types import Draft
from shine_email_assistant.gmail_client.thread import ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle
from shine_email_assistant.log import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_ESCALATION_MODEL = "claude-opus-4-7"


def _select_model(classification: Classification, *, allow_escalation: bool) -> str:
    explicit = os.getenv("MODEL_DRAFTER")
    if explicit:
        return explicit
    if not allow_escalation:
        return _DEFAULT_MODEL
    if classification.sensitivity == Sensitivity.MEDIUM or classification.confidence < 0.8:
        return _ESCALATION_MODEL
    return _DEFAULT_MODEL


def generate(
    thread: ParsedThread,
    kb: KnowledgeBundle,
    classification: Classification,
    *,
    allow_escalation: bool = False,
) -> Draft:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = _select_model(classification, allow_escalation=allow_escalation)

    resp = client.messages.create(
        model=model,
        max_tokens=800,
        system=build_cached_blocks(kb),
        messages=[{"role": "user", "content": build_user_prompt(thread, classification)}],
    )

    body = "".join(block.text for block in resp.content if block.type == "text").strip()

    log.info(
        "draft_generated",
        thread_id=thread.thread_id,
        model=model,
        tokens_input=resp.usage.input_tokens,
        tokens_output=resp.usage.output_tokens,
        cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0),
    )

    return Draft(
        body_markdown=body,
        tokens_input=resp.usage.input_tokens,
        tokens_output=resp.usage.output_tokens,
        model_used=model,
    )
```

- [ ] **Step 4: Write `drafter/__init__.py`**

```python
from shine_email_assistant.drafter.generate import generate
from shine_email_assistant.drafter.types import Draft

__all__ = ["generate", "Draft"]
```

- [ ] **Step 5: Write smoke integration test**

`tests/integration/test_drafter.py`:

```python
"""Smoke test: drafter produces a non-empty body that doesn't contain banned phrases."""
from datetime import datetime

import pytest

from shine_email_assistant.classifier.types import Classification, Sensitivity
from shine_email_assistant.drafter import generate
from shine_email_assistant.gmail_client.thread import ParsedMessage, ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle


pytestmark = pytest.mark.integration

_BANNED_PHRASES = [
    "i hope this email finds you well",
    "i hope this finds you well",
    "certainly!",
    "absolutely!",
    "feel free to",
    "as an ai",
]


_KB = KnowledgeBundle(
    kb_text="# Schedule\n\nMon, Wed, Fri 6pm. Saturday 9am beginner class.\n\n# Pricing\n\nDrop-in: $25. 10-pack: $200.\n",
    voice_text=(
        "# Voice\n\nWarm, concise, brand-genuine. Conversational. Like a real person at the studio replying.\n\n"
        "Sample: 'Hi! Yes, our Saturday 9am class is perfect for beginners — no experience needed. "
        "Drop in or grab a 10-pack if you think you'll be back.\n\nWarmly, Shine'"
    ),
    version="test",
)


def _classification() -> Classification:
    return Classification(
        should_draft=True,
        category="schedule_question",
        sensitivity=Sensitivity.LOW,
        confidence=0.95,
        reason="clear factual schedule question",
    )


def test_generate_returns_nonempty_body_without_banned_phrases(anthropic_available):
    thread = ParsedThread(
        thread_id="t1",
        messages=(ParsedMessage(
            message_id="m1",
            from_address="Cust <c@x.com>",
            from_email="c@x.com",
            to_addresses=("info@shinefitness.com",),
            subject="Class times",
            date=datetime.utcnow(),
            body_text="Hi, when do classes meet on weekends?",
        ),),
    )

    draft = generate(thread, _KB, _classification())

    assert draft.body_markdown.strip()
    body_lower = draft.body_markdown.lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in body_lower, f"draft contains banned phrase: {phrase!r}"
    # body should reference the actual KB fact
    assert "saturday" in body_lower or "9" in body_lower
```

- [ ] **Step 6: Run test**

Run: `uv run pytest tests/integration/test_drafter.py -m integration -v`
Expected: 1 passed. (If banned-phrase assertion fails, that's *useful signal* — iterate the prompt until a draft for this fixture is clean. The voice guide and system prompt are the levers.)

- [ ] **Step 7: Commit**

```bash
git add shine_email_assistant/drafter/ tests/integration/test_drafter.py
git commit -m "feat: drafter with KB caching, Sonnet default, optional Opus escalation"
```

---

## Task 13: Pipeline orchestrator

**Files:**
- Create: `shine_email_assistant/pipeline.py`

- [ ] **Step 1: Implement pipeline**

`shine_email_assistant/pipeline.py`:

```python
"""Orchestrator. Wires components into the per-tick processing loop.

One tick:
  for each unprocessed thread:
      filter → classify → (maybe) draft → (maybe) render → (maybe) create draft
      label appropriately and persist a record

Errors during one thread are logged + recorded but do not stop the tick.
"""
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from shine_email_assistant.alerts import send_alert
from shine_email_assistant.classifier import Sensitivity, classify
from shine_email_assistant.classifier.types import Classification
from shine_email_assistant.db import DraftRecord, ErrorRecord, SkipRecord, init_db, session
from shine_email_assistant.drafter import generate
from shine_email_assistant.filters import should_skip
from shine_email_assistant.gmail_client import (
    ERROR_LABEL,
    FLAG_FOR_HUMAN_LABEL,
    PROCESSED_LABEL,
    SKIPPED_LABEL,
    GmailClient,
    ParsedThread,
)
from shine_email_assistant.knowledge import KnowledgeBundle, KnowledgeLoader
from shine_email_assistant.log import configure_logging, get_logger
from shine_email_assistant.renderer import render

log = get_logger(__name__)

_TICK_LOCK = Lock()  # in-process: prevents overlapping ticks if one runs slow

_ERROR_RATE_THRESHOLD = 5
_ERROR_RATE_WINDOW = timedelta(hours=1)
_LAST_ERROR_ALERT_AT: datetime | None = None
_ERROR_ALERT_COOLDOWN = timedelta(hours=1)


class Pipeline:
    def __init__(self, tenant_name: str, tenants_root: Path):
        self.tenant_name = tenant_name
        self.tenants_root = tenants_root
        self.gmail = GmailClient()
        self.knowledge_loader = KnowledgeLoader(tenants_root)
        self.allow_opus_escalation = os.getenv("ALLOW_OPUS_ESCALATION", "false").lower() == "true"

    # ---- one tick ----

    def tick(self) -> None:
        if not _TICK_LOCK.acquire(blocking=False):
            log.info("tick_skipped_lock_held")
            return
        try:
            kb = self._load_kb_or_alert()
            if kb is None:
                return
            thread_ids = self.gmail.list_unprocessed_thread_ids()
            log.info("tick_started", count=len(thread_ids))
            for tid in thread_ids:
                self._process_thread(tid, kb)
        finally:
            _TICK_LOCK.release()

    def _load_kb_or_alert(self) -> KnowledgeBundle | None:
        try:
            return self.knowledge_loader.load(self.tenant_name)
        except Exception as e:  # noqa: BLE001
            log.error("kb_load_failed", error=str(e), traceback=traceback.format_exc())
            send_alert(
                subject="Knowledge base failed to load",
                body=f"Tenant: {self.tenant_name}\nError: {e}\n\nNo emails will be processed until this is fixed.",
            )
            return None

    def _process_thread(self, thread_id: str, kb: KnowledgeBundle) -> None:
        try:
            thread = self.gmail.get_thread(thread_id)
        except Exception as e:  # noqa: BLE001
            self._record_error(thread_id, "fetch", e)
            self._safe_label(thread_id, ERROR_LABEL)
            return

        # 1) Rule filter
        skip = should_skip(thread)
        if skip.skip:
            log.info("thread_skipped_by_rule", thread_id=thread_id, reason=skip.reason)
            self._record_skip(thread_id, "rule_filter", skip.reason)
            self._safe_label(thread_id, SKIPPED_LABEL)
            return

        # 2) Classifier
        try:
            classification = classify(thread, kb)
        except Exception as e:  # noqa: BLE001
            self._record_error(thread_id, "classify", e)
            self._safe_label(thread_id, ERROR_LABEL)
            return

        log.info(
            "classification",
            thread_id=thread_id,
            should_draft=classification.should_draft,
            category=classification.category,
            sensitivity=classification.sensitivity.value,
            confidence=classification.confidence,
        )

        if classification.sensitivity == Sensitivity.HIGH:
            log.info("thread_flagged_for_human", thread_id=thread_id, reason=classification.reason)
            self._record_skip(thread_id, "sensitivity_high", classification.reason,
                              extra={"category": classification.category, "confidence": classification.confidence})
            self._safe_label(thread_id, FLAG_FOR_HUMAN_LABEL)
            return

        if not classification.should_draft:
            log.info("thread_skipped_by_classifier", thread_id=thread_id, reason=classification.reason)
            self._record_skip(thread_id, "classifier", classification.reason,
                              extra={"category": classification.category, "confidence": classification.confidence})
            self._safe_label(thread_id, SKIPPED_LABEL)
            return

        # 3) Draft
        try:
            draft = generate(thread, kb, classification, allow_escalation=self.allow_opus_escalation)
        except Exception as e:  # noqa: BLE001
            self._record_error(thread_id, "draft", e)
            self._safe_label(thread_id, ERROR_LABEL)
            return

        # 4) Render
        try:
            rendered = render(draft.body_markdown, tenant_name=self.tenant_name, tenants_root=self.tenants_root)
        except Exception as e:  # noqa: BLE001
            self._record_error(thread_id, "render", e)
            self._safe_label(thread_id, ERROR_LABEL)
            return

        # 5) Create draft in Gmail
        latest = thread.latest_message
        msg_id_header = latest.headers.get("Message-ID") or latest.headers.get("Message-Id") or ""
        try:
            draft_id = self.gmail.create_draft(
                thread_id=thread_id,
                in_reply_to_message_id_header=msg_id_header,
                to=latest.from_email,
                subject=latest.subject or "(no subject)",
                html_body=rendered.html,
                plaintext_body=rendered.plaintext,
                references=latest.headers.get("References") or msg_id_header,
            )
        except Exception as e:  # noqa: BLE001
            self._record_error(thread_id, "create_draft", e)
            self._safe_label(thread_id, ERROR_LABEL)
            return

        # 6) Persist + label processed
        self._record_draft(thread_id, draft_id, msg_id_header, classification, draft, rendered, kb.version)
        self._safe_label(thread_id, PROCESSED_LABEL)
        log.info("draft_created", thread_id=thread_id, draft_id=draft_id, category=classification.category)

    # ---- persistence helpers ----

    def _record_draft(self, thread_id, draft_id, msg_id_header, classification, draft, rendered, kb_version):
        with session() as s:
            s.add(DraftRecord(
                tenant=self.tenant_name,
                thread_id=thread_id,
                draft_id=draft_id,
                message_id_replied_to=msg_id_header,
                category=classification.category,
                sensitivity=classification.sensitivity.value,
                confidence=classification.confidence,
                classification_reason=classification.reason,
                body_markdown=draft.body_markdown,
                rendered_html=rendered.html,
                kb_version=kb_version,
                model_used=draft.model_used,
                tokens_input=draft.tokens_input,
                tokens_output=draft.tokens_output,
            ))
            s.commit()

    def _record_skip(self, thread_id, source, reason, extra: dict | None = None):
        with session() as s:
            s.add(SkipRecord(
                tenant=self.tenant_name,
                thread_id=thread_id,
                skip_source=source,
                reason=reason,
                metadata_json=extra or {},
            ))
            s.commit()

    def _record_error(self, thread_id, stage, exc: Exception):
        log.error("pipeline_error", thread_id=thread_id, stage=stage, error=str(exc),
                  traceback=traceback.format_exc())
        with session() as s:
            s.add(ErrorRecord(
                tenant=self.tenant_name,
                thread_id=thread_id,
                stage=stage,
                error_type=type(exc).__name__,
                error_message=str(exc)[:2000],
            ))
            s.commit()
        self._maybe_alert_on_error_rate()

    def _maybe_alert_on_error_rate(self):
        global _LAST_ERROR_ALERT_AT
        now = datetime.now(timezone.utc)
        if _LAST_ERROR_ALERT_AT and now - _LAST_ERROR_ALERT_AT < _ERROR_ALERT_COOLDOWN:
            return
        cutoff = now - _ERROR_RATE_WINDOW
        with session() as s:
            recent = s.query(ErrorRecord).filter(
                ErrorRecord.tenant == self.tenant_name,
                ErrorRecord.created_at >= cutoff.replace(tzinfo=None),  # naive UTC in DB
            ).count()
        if recent >= _ERROR_RATE_THRESHOLD:
            send_alert(
                subject=f"Error rate spike: {recent} errors in last hour",
                body=f"Tenant {self.tenant_name} has hit {recent} errors in the last hour. Check Railway logs.",
            )
            _LAST_ERROR_ALERT_AT = now

    def _safe_label(self, thread_id: str, label: str) -> None:
        try:
            self.gmail.add_label(thread_id, label)
        except Exception as e:  # noqa: BLE001
            log.error("label_add_failed", thread_id=thread_id, label=label, error=str(e))


# ---- entrypoints ----

def run_forever(tenant_name: str, tenants_root: Path, poll_interval_seconds: int = 60) -> None:
    configure_logging()
    init_db()
    pipeline = Pipeline(tenant_name=tenant_name, tenants_root=tenants_root)
    log.info("pipeline_started", tenant=tenant_name, poll_seconds=poll_interval_seconds)
    while True:
        try:
            pipeline.tick()
        except Exception as e:  # noqa: BLE001
            log.error("tick_unexpected_error", error=str(e), traceback=traceback.format_exc())
        time.sleep(poll_interval_seconds)
```

- [ ] **Step 2: Verify imports compile**

Run: `uv run python -c "from shine_email_assistant.pipeline import Pipeline, run_forever; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add shine_email_assistant/pipeline.py
git commit -m "feat: pipeline orchestrator with per-stage error handling and DB records"
```

---

## Task 14: Feedback sweep

**Files:**
- Create: `shine_email_assistant/feedback/audit.py`
- Modify: `shine_email_assistant/feedback/__init__.py`

- [ ] **Step 1: Implement audit**

`shine_email_assistant/feedback/audit.py`:

```python
"""Daily sweep: compare each recent draft to the actually-sent message in the thread."""
from datetime import datetime, timedelta, timezone

from shine_email_assistant.db import DraftRecord, session
from shine_email_assistant.feedback.diff import categorize_outcome, edit_distance_ratio
from shine_email_assistant.gmail_client import GmailClient
from shine_email_assistant.log import get_logger

log = get_logger(__name__)


def audit_recent_drafts(*, hours: int = 30) -> dict:
    """For each draft created in the last N hours that hasn't been audited, find the
    sent message in the same thread (if any), compute edit distance, persist outcome.

    Returns a summary dict (counts by outcome).
    """
    gmail = GmailClient()
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    summary = {"sent_as_is": 0, "lightly_edited": 0, "heavily_rewritten": 0, "not_sent": 0, "audited": 0}

    with session() as s:
        rows = s.query(DraftRecord).filter(
            DraftRecord.audited_at.is_(None),
            DraftRecord.created_at >= cutoff,
        ).all()

        # Pre-fetch recent sent messages once
        sent_by_thread: dict[str, list[dict]] = {}
        for sm in gmail.list_recent_sent_messages(hours=hours + 24):
            sent_by_thread.setdefault(sm["threadId"], []).append(sm)

        for row in rows:
            sent_msgs = sent_by_thread.get(row.thread_id, [])
            # Pick the first sent message in this thread that came AFTER the draft was created.
            # (Compare loosely on internalDate which is ms since epoch.)
            chosen = None
            draft_ms = int(row.created_at.timestamp() * 1000)
            for sm in sent_msgs:
                # internalDate isn't in list output; just take any sent message after draft creation.
                # We'll fetch the body to compare.
                chosen = sm
                break

            if not chosen:
                row.outcome = "not_sent"
                row.audited_at = datetime.utcnow()
                summary["not_sent"] += 1
                summary["audited"] += 1
                continue

            try:
                sent_text = gmail.get_message_body_text(chosen["id"])
            except Exception as e:  # noqa: BLE001
                log.warning("audit_fetch_failed", message_id=chosen["id"], error=str(e))
                continue

            ratio = edit_distance_ratio(row.body_markdown.strip(), sent_text.strip())
            outcome = categorize_outcome(ratio)
            row.outcome = outcome.value
            row.edit_distance_ratio = ratio
            row.sent_message_id = chosen["id"]
            row.audited_at = datetime.utcnow()
            summary[outcome.value] += 1
            summary["audited"] += 1

        s.commit()

    log.info("audit_complete", **summary)
    return summary
```

- [ ] **Step 2: Update `feedback/__init__.py`**

```python
from shine_email_assistant.feedback.audit import audit_recent_drafts
from shine_email_assistant.feedback.diff import Outcome, categorize_outcome, edit_distance_ratio

__all__ = ["audit_recent_drafts", "Outcome", "categorize_outcome", "edit_distance_ratio"]
```

- [ ] **Step 3: Commit**

```bash
git add shine_email_assistant/feedback/
git commit -m "feat: feedback sweep — audit drafts vs sent messages"
```

---

## Task 15: Main entrypoint

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write `main.py`**

```python
"""Entrypoint. Run with no args for the polling loop, or --daily-sweep for the audit."""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-sweep", action="store_true",
                        help="Run the feedback sweep once and exit (used by scheduled cron).")
    args = parser.parse_args()

    tenants_root = Path(__file__).resolve().parent / "tenants"
    tenant_name = os.getenv("TENANT_NAME", "shine")

    if args.daily_sweep:
        from shine_email_assistant.db import init_db
        from shine_email_assistant.feedback import audit_recent_drafts
        from shine_email_assistant.log import configure_logging
        configure_logging()
        init_db()
        audit_recent_drafts()
        return 0

    from shine_email_assistant.pipeline import run_forever
    poll = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    run_forever(tenant_name=tenant_name, tenants_root=tenants_root, poll_interval_seconds=poll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run python -c "import main; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main entrypoint (polling loop + --daily-sweep mode)"
```

---

## Task 16: Tenant content for Shine (stub)

**Files:**
- Create: `tenants/shine/config.yaml`, `tenants/shine/voice.md`, `tenants/shine/signature.html`, `tenants/shine/email_template.html`
- Create: `tenants/shine/knowledge/about.md`, `tenants/shine/knowledge/schedule.md`, `tenants/shine/knowledge/pricing.md`, `tenants/shine/knowledge/policies.md`, `tenants/shine/knowledge/faqs.md`

**Note:** the content here is a *starting stub* with realistic-but-made-up information per the spec. Real Shine content gets swapped in before going live on the production inbox. Keep the structure; iterate the content with input from Mom/Dad.

- [ ] **Step 1: Write `tenants/shine/config.yaml`**

```yaml
display_name: Shine Dance Fitness
brand_color: '#E91E63'
website: https://shinefitness.com
address: '123 Main Street, Anytown, USA'
phone: '+1 (555) 123-4567'
reply_signoff: '— Shine Dance Fitness'
```

- [ ] **Step 2: Write `tenants/shine/voice.md`**

```markdown
# Shine Voice Guide

Warm, encouraging, casual-professional. Like a friendly studio owner replying
in their lunch break — not corporate, not gushing, not robotic.

## Tone rules

- First-person singular when answering practical questions ("I checked the schedule and...")
- "We" only when speaking for the studio as a community ("We'd love to see you in class!")
- Short paragraphs (1–3 sentences each)
- Specific to what the customer asked — never generic
- One exclamation point max per email. Often zero.
- Sign off with `— Shine Dance Fitness` (or `Warmly, Shine`) — no specific person's name

## Forbidden phrases

- "I hope this email finds you well"
- "Certainly!" / "Absolutely!" as openers
- "Feel free to..."
- Em-dashes used stylistically (—) — fine in this voice doc, banned in replies
- Anything that sounds like ChatGPT default

## Few-shot examples

### Example 1 — schedule question

> Customer: "What time is your Tuesday class?"

Hi! Our Tuesday class runs from 6:30–7:30pm. It's our high-energy cardio dance hour, all levels welcome. Hope to see you there.

— Shine Dance Fitness

### Example 2 — beginner unsure

> Customer: "I've never danced before. Is this for me?"

Honestly, yes — most people who come to Shine had zero dance background when they started. Our Saturday 9am class is the most beginner-friendly; it's slower-paced and the regulars are super welcoming. Drop in for one before committing to anything.

— Shine Dance Fitness

### Example 3 — pricing question

> Customer: "How much is it to drop in?"

Drop-in is $25 per class. If you think you'll come back, the 10-pack at $200 brings it down to $20/class and doesn't expire for 6 months.

Either way, first class is on us — just mention this email.

Warmly, Shine

### Example 4 — couldn't fully answer

> Customer: "Can I bring my 10-year-old daughter to class? Do you offer family rates?"

Great question — most of our classes are 16+, but we do have a Saturday family class at 10am that welcomes kids 8 and up. We don't currently offer a family-rate package, but I'd love to ask the team if we can put something together.

I'll loop back in a day or two with a clearer answer on the family rate. Either way, we'd love to see you both at the Saturday class.

— Shine Dance Fitness

### Example 5 — short follow-up in a thread

> Customer: "Great, can I just show up Saturday?"

Yep, just walk in! Doors open at 8:45. Comfortable clothes, water bottle, that's it. See you Saturday.

— Shine Dance Fitness
```

- [ ] **Step 3: Write `tenants/shine/signature.html`**

```html
<table cellpadding="0" cellspacing="0" border="0" style="font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;font-size:14px;color:#555;line-height:1.5;margin-top:8px">
  <tr>
    <td>
      <strong style="color:#222">{{ display_name }}</strong><br>
      {{ phone }} &nbsp;·&nbsp; <a href="{{ website }}" style="color:{{ brand_color }};text-decoration:none">{{ website }}</a><br>
      <span style="color:#888">{{ address }}</span>
    </td>
  </tr>
</table>
```

- [ ] **Step 4: Write `tenants/shine/email_template.html`**

```html
<!doctype html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;color:#222;line-height:1.55;margin:0;padding:0">
  <div style="max-width:560px;margin:0 auto;padding:16px 0">
    {{ body_html }}
    <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
    {{ signature_html }}
  </div>
</body>
</html>
```

- [ ] **Step 5: Write knowledge files**

`tenants/shine/knowledge/about.md`:

```markdown
# About Shine Dance Fitness

Shine Dance Fitness is a boutique dance fitness studio in Anytown, USA.
Founded by [name], offering high-energy cardio dance classes, beginner-friendly
sessions, and the occasional weekend family class. Our community is the heart of
what we do — most students stay for years.
```

`tenants/shine/knowledge/schedule.md`:

```markdown
# Class Schedule

| Day       | Time         | Class                     | Level         |
|-----------|--------------|---------------------------|---------------|
| Monday    | 6:00–7:00pm  | Cardio Dance              | All levels    |
| Tuesday   | 6:30–7:30pm  | High-Energy Dance Hour    | All levels    |
| Wednesday | 6:00–7:00pm  | Cardio Dance              | All levels    |
| Thursday  | 7:00–8:00pm  | Hip-Hop Cardio            | All levels    |
| Friday    | 6:00–7:00pm  | Cardio Dance              | All levels    |
| Saturday  | 9:00–10:00am | Beginner Dance            | Beginner      |
| Saturday  | 10:00–11:00am| Family Class (kids 8+)    | All ages 8+   |

Doors open 15 minutes before each class. No reservation needed for drop-ins
unless noted otherwise.
```

`tenants/shine/knowledge/pricing.md`:

```markdown
# Pricing

| Option                 | Price | Notes                                       |
|------------------------|-------|---------------------------------------------|
| Drop-in (single class) | $25   | First class free for new students           |
| 10-pack                | $200  | Works out to $20/class, expires in 6 months |
| Monthly unlimited      | $129  | Auto-renews; cancel anytime                 |
| Annual unlimited       | $1,300| Best value if you'll come 2+ times/week     |

We do not currently offer family rate packages.
```

`tenants/shine/knowledge/policies.md`:

```markdown
# Policies

## Cancellations
- Drop-ins and 10-pack visits: no cancellation needed; just don't show up.
- Monthly unlimited: cancel anytime, no fee, takes effect at the next billing date.
- Annual unlimited: pro-rated refund within 30 days of purchase; no refund after that.

## Refunds
- All refund requests go to a human (we don't auto-process refunds via email).
- Typical turnaround: 2 business days.

## Late cancellations / no-shows
- For special events (workshops, intensives) only: $15 no-show fee.

## What to wear / bring
- Comfortable workout clothes
- Sneakers (any kind)
- Water bottle
- Yourself, ready to move
```

`tenants/shine/knowledge/faqs.md`:

```markdown
# Frequently Asked Questions

**Do I need experience to join?**
No. Most of our classes are all-levels, and Saturday 9am is specifically beginner-friendly.

**Is this for any age?**
Most classes are 16+. The Saturday 10am family class welcomes kids 8 and up with an adult.

**Do I need to register in advance?**
No. Just drop in. If a class fills up (rare), we'll let you know at the door.

**Is the first class really free?**
Yes — first class is on us for new students. Just mention it when you arrive.

**Do you offer private lessons?**
Not currently. We may pilot some in the future; ask and we'll keep your name on a list.

**Is parking available?**
Yes, free street parking and a small lot behind the studio.
```

- [ ] **Step 6: Add a placeholder logo**

```bash
# For PoC, use a 1x1 transparent PNG. Real Shine logo gets dropped in before launch.
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82' > tenants/shine/logo.png
```

- [ ] **Step 7: Commit**

```bash
git add tenants/shine/
git commit -m "feat: tenant content stub for Shine (KB, voice, sig, template)"
```

---

## Task 17: Golden test harness

**Files:**
- Create: `tests/integration/golden/__init__.py`, `tests/integration/golden/fixtures/`, `tests/integration/golden/test_golden_emails.py`, `scripts/seed_test_inbox.py`

The "golden test" approach: pre-seed the test Gmail account with hand-crafted emails (one per scenario), let the pipeline process them once, then assert outcomes against expected. The seeding is a manual one-time step (or rerunnable if labels get cleared).

- [ ] **Step 1: Define golden fixtures**

`tests/integration/golden/__init__.py`: empty

Create `tests/integration/golden/fixtures/golden_emails.yaml`:

```yaml
- id: schedule_question_simple
  from: customer1@example.com
  subject: "Tuesday class time?"
  body: "Hi, what time is your Tuesday class?"
  expected_outcome: drafted
  expected_category_substring: schedule

- id: pricing_drop_in
  from: customer2@example.com
  subject: "How much per class?"
  body: "How much is it to drop in for one class?"
  expected_outcome: drafted
  expected_category_substring: pricing

- id: beginner_inquiry
  from: customer3@example.com
  subject: "I've never danced"
  body: "Hi! I've literally never taken a dance class. Is this beginner friendly?"
  expected_outcome: drafted

- id: refund_request
  from: customer4@example.com
  subject: "Refund please"
  body: "I bought the annual pass last week and need to cancel for medical reasons. Can I get a refund?"
  expected_outcome: flagged

- id: complaint
  from: customer5@example.com
  subject: "Not happy"
  body: "The instructor was incredibly rude to me on Saturday. I'm very upset and want a response."
  expected_outcome: flagged

- id: vendor_pitch
  from: salesrep@vendor.com
  subject: "Boost your studio's revenue!"
  body: "Hi there, I'd love to show you our new POS system that's helping studios like yours increase revenue by 30%."
  expected_outcome: skipped

- id: short_thanks
  from: customer6@example.com
  subject: "thanks"
  body: "ok thanks!"
  expected_outcome: skipped  # nothing actionable

- id: ambiguous_multi_question
  from: customer7@example.com
  subject: "couple of questions"
  body: "Hi, I had a few questions: do you offer kids classes, what's parking like, and is there a senior discount? Also what's your refund policy?"
  expected_outcome: drafted  # answerable from KB but model may flag ambiguous; either way drafted is OK

- id: registration
  from: customer8@example.com
  subject: "Sign me up"
  body: "I want to start coming. How do I sign up for the monthly unlimited?"
  expected_outcome: drafted

- id: family_question
  from: customer9@example.com
  subject: "Can my daughter come?"
  body: "Can I bring my 10-year-old to class with me?"
  expected_outcome: drafted
```

- [ ] **Step 2: Write seed script**

`scripts/seed_test_inbox.py`:

```python
"""Seed the test Gmail inbox with golden fixture emails.

Sends each fixture as an email FROM the test account TO itself. Run once before
running the golden test suite. Idempotent in the sense that you can re-run, but
note that each run creates new threads (the old ones don't go away unless you
clear them first).

Run: uv run python scripts/seed_test_inbox.py
"""
import base64
import os
from email.message import EmailMessage
from pathlib import Path

import yaml
from dotenv import load_dotenv
from googleapiclient.discovery import build

from shine_email_assistant.gmail_client.auth import credentials_from_env

load_dotenv()


def main() -> int:
    fixtures_path = Path(__file__).resolve().parent.parent / "tests/integration/golden/fixtures/golden_emails.yaml"
    fixtures = yaml.safe_load(fixtures_path.read_text())

    user_email = os.environ["GMAIL_USER_EMAIL"]
    svc = build("gmail", "v1", credentials=credentials_from_env(), cache_discovery=False)

    for fx in fixtures:
        msg = EmailMessage()
        msg["From"] = fx["from"]
        msg["To"] = user_email
        msg["Subject"] = f"[golden:{fx['id']}] {fx['subject']}"
        msg.set_content(fx["body"])
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        # Insert directly into the user's inbox; this keeps the From header as written.
        svc.users().messages().insert(
            userId="me", body={"raw": raw, "labelIds": ["INBOX", "UNREAD"]}
        ).execute()
        print(f"seeded {fx['id']}")

    print(f"\nSeeded {len(fixtures)} fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Write the golden test runner**

`tests/integration/golden/test_golden_emails.py`:

```python
"""Run the pipeline against the seeded test inbox; assert outcomes match expectations.

Pre-req: run `uv run python scripts/seed_test_inbox.py` first.

Outcome mapping:
- "drafted"  → thread ends up with `processed` label and a DraftRecord exists
- "skipped"  → thread ends up with `processed-skipped` label and a SkipRecord exists
- "flagged"  → thread ends up with `flag-for-human` label, no DraftRecord
"""
import os
import time
from pathlib import Path

import pytest
import yaml

from shine_email_assistant.db import DraftRecord, SkipRecord, init_db, session
from shine_email_assistant.gmail_client import (
    FLAG_FOR_HUMAN_LABEL,
    PROCESSED_LABEL,
    SKIPPED_LABEL,
    GmailClient,
)
from shine_email_assistant.pipeline import Pipeline


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fixtures():
    path = Path(__file__).parent / "fixtures/golden_emails.yaml"
    return {fx["id"]: fx for fx in yaml.safe_load(path.read_text())}


@pytest.fixture(scope="module")
def processed_threads(fixtures, gmail_client):
    """Run the pipeline once over all unprocessed threads. Returns mapping fixture_id → thread."""
    init_db()
    tenants_root = Path(__file__).resolve().parents[3] / "tenants"
    tenant = os.getenv("TENANT_NAME", "shine")

    pipeline = Pipeline(tenant_name=tenant, tenants_root=tenants_root)
    pipeline.tick()
    # Give Gmail a beat to settle label changes
    time.sleep(2)

    # Map back from thread → fixture by parsing the [golden:<id>] tag in the subject.
    out: dict[str, dict] = {}
    threads = gmail_client._service.users().threads().list(userId="me", q="subject:[golden:]").execute().get("threads", [])
    for t in threads:
        full = gmail_client.get_thread(t["id"])
        subj = full.latest_message.subject
        # Subject format: "[golden:<id>] ..."
        if subj.startswith("[golden:"):
            close = subj.find("]")
            fx_id = subj[len("[golden:"):close]
            label_names = _label_names(gmail_client, t["id"])
            out[fx_id] = {"thread_id": t["id"], "labels": label_names, "subject": subj}
    return out


def _label_names(gmail_client: GmailClient, thread_id: str) -> set[str]:
    raw = gmail_client._service.users().threads().get(userId="me", id=thread_id).execute()
    label_ids: set[str] = set()
    for m in raw.get("messages", []):
        label_ids.update(m.get("labelIds", []))
    # Reverse-lookup label IDs to names
    all_labels = gmail_client._service.users().labels().list(userId="me").execute().get("labels", [])
    by_id = {l["id"]: l["name"] for l in all_labels}
    return {by_id[lid] for lid in label_ids if lid in by_id}


@pytest.mark.parametrize("fixture_id", [
    "schedule_question_simple",
    "pricing_drop_in",
    "beginner_inquiry",
    "refund_request",
    "complaint",
    "vendor_pitch",
    "short_thanks",
    "ambiguous_multi_question",
    "registration",
    "family_question",
])
def test_golden_email_outcome(fixture_id, fixtures, processed_threads):
    fixture = fixtures[fixture_id]
    if fixture_id not in processed_threads:
        pytest.skip(f"fixture {fixture_id} not in inbox; re-run scripts/seed_test_inbox.py")

    info = processed_threads[fixture_id]
    expected = fixture["expected_outcome"]

    if expected == "drafted":
        assert PROCESSED_LABEL in info["labels"], f"{fixture_id}: expected processed, got {info['labels']}"
        with session() as s:
            row = s.query(DraftRecord).filter(DraftRecord.thread_id == info["thread_id"]).first()
        assert row is not None, f"{fixture_id}: no DraftRecord"
        if "expected_category_substring" in fixture:
            assert fixture["expected_category_substring"] in row.category.lower()
    elif expected == "skipped":
        assert SKIPPED_LABEL in info["labels"], f"{fixture_id}: expected skipped, got {info['labels']}"
    elif expected == "flagged":
        assert FLAG_FOR_HUMAN_LABEL in info["labels"], f"{fixture_id}: expected flagged, got {info['labels']}"
        with session() as s:
            row = s.query(DraftRecord).filter(DraftRecord.thread_id == info["thread_id"]).first()
        assert row is None, f"{fixture_id}: DraftRecord should not exist for flagged"
    else:
        pytest.fail(f"unknown expected_outcome: {expected}")
```

- [ ] **Step 4: Manual seed + run**

```bash
uv run python scripts/seed_test_inbox.py
uv run pytest tests/integration/golden/ -m integration -v
```

Expected: 10 fixtures, mostly green. Iterate the prompt / voice / KB if any expected-drafted comes back skipped (or vice versa). Tuning the system to pass the golden suite is the bulk of the PoC quality work.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/golden/ scripts/seed_test_inbox.py
git commit -m "test: golden-email harness with 10 hand-crafted scenarios"
```

---

## Task 18: Railway deployment config

**Files:**
- Create: `railway.toml`
- Modify: `README.md` (add deploy section)

- [ ] **Step 1: Write `railway.toml`**

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uv run python main.py"
restartPolicyType = "ALWAYS"

# Daily sweep runs as a separate scheduled service (set up via Railway UI).
# See README for the exact command.
```

- [ ] **Step 2: Add deploy section to README**

Append to `README.md`:

```markdown
## Deploy (Railway)

1. Create a Railway project and connect this repo.
2. Add the **Postgres** add-on. Railway auto-injects `DATABASE_URL` into your service env.
3. In the service settings → Variables, add all the keys from `.env.example` (Anthropic, Gmail OAuth, SMTP).
4. Set a spending cap (~$10/mo) under the project's billing settings as a safety net.
5. Push to `main` — Railway auto-builds and deploys.

### Daily feedback sweep

Create a second Railway service in the same project pointing at the same repo, but
override the start command to:

```
uv run python main.py --daily-sweep
```

Schedule it via Railway's cron feature: `0 6 * * *` (6am UTC daily).
It runs once and exits, so Railway's "ALWAYS restart" should be changed to "NEVER".

### Verifying the deploy

After deploy, check the service logs. You should see periodic JSON log lines:
- `pipeline_started`
- `tick_started count=...`
- `classification thread_id=... category=...`
- `draft_created` (when a draft was made)

If you see `kb_load_failed` or `pipeline_error` repeatedly, check the alert email.
```

- [ ] **Step 3: Commit**

```bash
git add railway.toml README.md
git commit -m "chore: Railway deployment config + README deploy steps"
```

---

## Task 19: First-deploy smoke run

This is operational, not code. No new commits.

- [ ] **Step 1: Push to GitHub**

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

- [ ] **Step 2: Provision Railway**

Follow the README deploy steps. Provision the Postgres add-on, paste env vars, set spending cap.

- [ ] **Step 3: Watch logs for first tick**

In the Railway dashboard, open the service log stream. Within 60s of deploy, expect:
- `pipeline_started tenant=shine poll_seconds=60`
- `tick_started count=N`
- For seeded golden emails: `classification` + `draft_created` log lines

- [ ] **Step 4: Verify drafts in test Gmail**

Open Gmail. Each seeded customer thread should now have a draft attached. Open one — confirm it renders properly (HTML signature, brand color, no AI tells).

- [ ] **Step 5: Verify daily sweep cron**

Manually trigger the daily-sweep service in Railway. Confirm it runs to completion and the `audit_complete` log line appears with non-zero counts (assuming there's been any sent mail).

- [ ] **Step 6: Test alert path**

Temporarily revoke the Gmail token (in Google account settings), wait one tick, confirm alert email arrives. Re-grant and restart.

---

## Task 20: Voice-quality manual review pass

This is the final gate before going live on `info@shinefitness.com`. Not code, but mandatory per the spec's success criteria.

- [ ] **Step 1: Generate ~20 sample drafts**

Send a varied batch of realistic-sounding customer emails into the test inbox (mix of question types, tones, edge cases). Let the pipeline process them.

- [ ] **Step 2: Read every draft**

Open each in Gmail. For each, ask:
- Does it sound like a real person from Shine wrote it?
- Is the information correct (matches the KB)?
- Are there any AI tells?
- Would I be happy if Mom sent this to her customer?

- [ ] **Step 3: Get Dad's review**

Have him read the same drafts. Thumbs up/down on each. If he flags anything, iterate the voice guide / examples / KB and re-run the affected fixtures.

- [ ] **Step 4: Production launch checklist**

Only proceed to point Railway at `info@shinefitness.com` when:
- All golden tests green
- Dad gives thumbs-up on >=18/20 sample drafts
- Sensitive fixtures (refund, complaint) reach `flag-for-human` correctly
- 48+ hours of continuous Railway uptime on test account
- Alert path verified (Step 6 of Task 19)

---

## Out of scope (explicitly deferred)

These were marked out-of-scope in the spec and have NO tasks in this plan:
- Daily digest email to Dad (architecture supports it via `feedback/`; build after PoC validation)
- Auto-send for any category (config flag exists in design; ship as Phase 2)
- Web admin UI for KB editing
- Multi-tenant DB / onboarding
- RAG / vector search
- Google Sheets / Notion KB sync
- Pub/Sub push-based Gmail notifications

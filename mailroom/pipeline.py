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

from mailroom.alerts import send_alert
from mailroom.classifier import Sensitivity, classify
from mailroom.db import DraftRecord, ErrorRecord, SkipRecord, init_db, session
from mailroom.drafter import generate
from mailroom.filters import should_skip
from mailroom.gmail_client import (
    ERROR_LABEL,
    FLAG_FOR_HUMAN_LABEL,
    PROCESSED_LABEL,
    SKIPPED_LABEL,
    GmailClient,
)
from mailroom.knowledge import KnowledgeBundle, KnowledgeLoader
from mailroom.log import configure_logging, get_logger
from mailroom.renderer import render

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
            self._process_thread_inner(thread_id, kb)
        except Exception as e:  # noqa: BLE001
            log.error(
                "process_thread_unexpected",
                thread_id=thread_id,
                error=str(e),
                traceback=traceback.format_exc(),
            )
            self._safe_label(thread_id, ERROR_LABEL)

    def _process_thread_inner(self, thread_id: str, kb: KnowledgeBundle) -> None:
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
                to=latest.from_address or latest.from_email,
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
        # Note: the draft already exists in Gmail. We MUST apply PROCESSED_LABEL
        # even if DB persistence fails, otherwise we'd double-draft on the next tick.
        try:
            self._record_draft(thread_id, draft_id, msg_id_header, classification, draft, rendered, kb.version)
        except Exception as e:  # noqa: BLE001
            log.error(
                "draft_record_failed",
                thread_id=thread_id,
                draft_id=draft_id,
                error=str(e),
                traceback=traceback.format_exc(),
            )
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

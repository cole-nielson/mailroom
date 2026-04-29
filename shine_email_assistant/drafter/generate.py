"""Generate a draft body for one thread."""
import os
from functools import lru_cache

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


@lru_cache
def _client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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
    model = _select_model(classification, allow_escalation=allow_escalation)

    resp = _client().messages.create(
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

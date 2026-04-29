"""Call Claude to classify a thread. Returns a Classification."""
import json
import os
from functools import lru_cache

from anthropic import Anthropic

from shine_email_assistant.classifier.prompt import SYSTEM_PROMPT, build_user_prompt
from shine_email_assistant.classifier.types import Classification, Sensitivity
from shine_email_assistant.gmail_client.thread import ParsedThread
from shine_email_assistant.knowledge.loader import KnowledgeBundle
from shine_email_assistant.log import get_logger

log = get_logger(__name__)


_DEFAULT_MODEL = "claude-sonnet-4-6"


@lru_cache
def _client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def classify(thread: ParsedThread, kb: KnowledgeBundle, *, model: str | None = None) -> Classification:
    client = _client()
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
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("classifier_retry_json_parse_failed", thread_id=thread.thread_id, raw=text[:500])
            raise ValueError(
                f"Classifier returned non-JSON after retry. First 200 chars: {text[:200]!r}"
            ) from exc

    return Classification(
        should_draft=bool(data["should_draft"]),
        category=str(data["category"]),
        sensitivity=Sensitivity(data["sensitivity"]),
        confidence=float(data["confidence"]),
        reason=str(data.get("reason", "")),
    )

"""Drafter prompt. Body-only output — no signature, no HTML, no salutation boilerplate."""
from mailroom.classifier.types import Classification
from mailroom.gmail_client.thread import ParsedThread
from mailroom.knowledge.loader import KnowledgeBundle


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

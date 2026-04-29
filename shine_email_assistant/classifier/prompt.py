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

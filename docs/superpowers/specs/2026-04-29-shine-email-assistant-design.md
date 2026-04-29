# Shine Email Assistant — Design Spec

**Date:** 2026-04-29
**First customer:** Shine Dance Fitness (shinefitness.com)
**Status:** Design approved, ready for implementation planning

---

## Problem

Small businesses with public-facing inboxes (`info@`, `contact@`, `hello@`) get a steady stream of repetitive questions — hours, pricing, schedules, "is this right for me," basic policy stuff — that all need a response, all sound personal when answered well, and all eat up real human time. The current options are bad: someone (often the owner or a family member) burns hours each week writing the same kinds of replies, or messages sit unanswered and the business loses leads and looks unresponsive.

Generic AI tools don't solve this because they don't know the business, don't sound like the brand, and aren't safely connected to the actual inbox.

## What we're building

An AI email assistant that:

1. Connects to a business's Gmail account
2. Reads incoming emails on a polling cycle
3. Decides which deserve a reply (with rule + LLM gating)
4. Writes high-quality, on-brand draft replies grounded in a per-business knowledge base
5. Saves those replies as Gmail drafts attached to the original thread, for a human to review and send

The first customer is Shine Dance Fitness, owned by the developer's mother, run operationally by the developer's father. PoC happens against a test Gmail account; production launches against `info@shinefitness.com` in **draft-only** mode (every reply human-reviewed). After weeks of validated draft quality, narrow categories may graduate to selective auto-send while sensitive categories stay draft-only forever.

The architecture is built single-tenant first, but with clean per-component boundaries so multi-tenant SaaS for similar small businesses (boutique fitness, local services) is a config + database change, not a rewrite.

## Quality bar

The drafts must feel real:
- Brand's actual voice
- Proper HTML email formatting
- Tasteful, branded signature block
- No AI tells ("I hope this email finds you well," "Certainly!", excessive enthusiasm, "The Team" sounding hollow)
- Information grounded in the business's own reference docs, not guessed

If a draft would be embarrassing to send, the system has failed. **Better to flag for a human and write nothing than to draft something generic.**

---

## Design principles

1. **Gmail-native UX.** The product surface is the Gmail Drafts folder. No new tool for Dad to learn.
2. **Draft-only by default.** Auto-send is opt-in per category, never the default, and never available for sensitive categories.
3. **Tenant isolation via clean boundaries.** Today: hardcoded one tenant. Tomorrow: same code, different `tenant_id`. Per-tenant content (KB, voice, signature, brand) lives in `tenants/<name>/`.
4. **Avoid overengineering.** Five well-bounded components, not fifteen. Add complexity only when data shows it's needed.
5. **YAGNI on speculative features.** No web admin UI, no RAG, no fancy auth — until they're earning their keep.
6. **Real over mocked in tests.** The pieces most likely to break (Gmail, Claude) are the pieces we test against directly.

---

## High-level architecture

```
                    ┌─────────────────────────────┐
                    │   Always-on cloud service   │
                    │       (Railway, ~$5/mo)     │
                    └──────────────┬──────────────┘
                                   │
                                   │ poll every 60s
                                   ▼
                    ┌─────────────────────────────┐
                    │        pipeline.py          │  ← orchestrator
                    └──┬──────┬──────┬──────┬─────┘
                       │      │      │      │
        ┌──────────────┘      │      │      └─────────────┐
        ▼                     ▼      ▼                    ▼
  ┌──────────┐         ┌──────────┐ ┌──────────┐   ┌────────────┐
  │  gmail_  │         │ filters/ │ │drafter/  │   │ feedback/  │
  │  client/ │         │classifier│ │          │   │            │
  │          │         │          │ │ Claude + │   │ daily diff │
  │ list,    │         │ rule +   │ │ KB +     │   │ of draft   │
  │ get,     │         │ LLM gate │ │ thread + │   │ vs sent,   │
  │ draft,   │         │          │ │ voice    │   │ stored     │
  │ label    │         │          │ │          │   │ for tuning │
  └──────────┘         └──────────┘ └────┬─────┘   └────────────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │  knowledge/  │  ← per tenant
                                  │              │
                                  │ load all .md │
                                  │ from tenant  │
                                  │ folder, cache│
                                  └──────────────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │  renderer/   │  ← presentation
                                  │              │
                                  │ wrap LLM body│
                                  │ in HTML +    │
                                  │ signature.   │
                                  └──────────────┘
                                         │
                                         ▼
                              (back to gmail_client.create_draft)

         ┌─────────────────────────────────────────────────┐
         │   tenants/shine/                                │
         │     ├── knowledge/   (md files)                 │
         │     ├── voice.md     (style + few-shot examples)│
         │     ├── signature.html                          │
         │     ├── email_template.html                     │
         │     ├── logo.png                                │
         │     └── config.yaml  (brand colors, contact)    │
         └─────────────────────────────────────────────────┘

   Postgres (Railway add-on): drafts log, classifications, feedback metrics
```

Each box is one isolated component with a clear interface. Internals can change without breaking other components.

---

## Components

### `gmail_client/`
**Job:** Wrap Gmail API. The only place in the codebase that knows about Gmail.

**Interface:**
- `list_unprocessed_threads()` → list of thread IDs not yet handled (excludes Promotions/Updates, excludes ones with our `processed` label)
- `get_thread(id)` → structured thread (messages, headers, latest sender, has-existing-draft flag)
- `create_draft(thread_id, html, plaintext_fallback, in_reply_to)` → creates draft attached to thread
- `add_label(thread_id, label)` → tag for tracking state
- `list_recent_sent()` → for feedback loop, fetches sent messages from last N hours

**Dependencies:** `google-api-python-client`, OAuth refresh token from env.

### `filters/`
**Job:** Cheap rule-based pre-filter. Skip obvious non-candidates with zero LLM cost.

**Interface:**
- `should_skip(thread)` → `(bool, reason)`

**Rules:**
- Latest message is from us (we're not replying to ourselves)
- Has `List-Unsubscribe` header (mailing list)
- Sender matches automation pattern (`noreply@*`, `no-reply@*`, `mailer-daemon@*`, etc.)
- Has existing human draft on the thread (don't overwrite Dad's work)

### `classifier/`
**Job:** LLM-powered gate. Decides whether to draft, what category, sensitivity, confidence.

**Interface:**
- `classify(thread, kb)` → `Classification`

**Returns:**
```python
Classification(
    should_draft: bool,
    category: str,        # "schedule_question" | "pricing" | "registration" |
                          # "complaint" | "refund" | "ambiguous" |
                          # "not_replyable" | "general_question" | ...
    sensitivity: str,     # "low" | "medium" | "high"
    confidence: float,    # 0.0 to 1.0
    reason: str           # for logging / tuning
)
```

**Hard rules applied to output:**
- `sensitivity == "high"` → never draft, label `flag-for-human`
- `should_draft == False` → label `processed-skipped`, log reason

**Model:** Claude Sonnet 4.6, single call.

### `drafter/`
**Job:** Generate the body text of the reply. Body only — no signature, no HTML wrapping.

**Interface:**
- `generate(thread, kb, voice, classification)` → `Draft(body_markdown, internal_notes)`

**Prompt structure (with caching):**
- System prompt (cached): system-wide instructions, tone rules, "no AI tells" guidance
- KB content (cached): `tenants/<name>/knowledge/*.md` concatenated
- Voice guide (cached): `tenants/<name>/voice.md` with few-shot examples
- Per-request: thread context + classification

**Model selection (configurable):**
- Default: Sonnet 4.6 for everything
- Optional escalation: Opus 4.7 for `sensitivity == "medium"` or `confidence < 0.8` (toggle off in PoC, evaluate before enabling)

### `knowledge/`
**Job:** Load and cache per-tenant KB content from disk.

**Interface:**
- `load(tenant_name)` → `KnowledgeBundle(kb_text, voice_text, examples)`

**Implementation:** read all `.md` files from `tenants/<name>/knowledge/`, concatenate. Read `voice.md` separately. Cache in memory; invalidate on file mtime change.

**Future evolution:** swap internals to read from Google Sheets, Notion, or a web admin without touching consumers.

### `renderer/`
**Job:** Wrap the LLM's body markdown in styled HTML + signature template.

**Interface:**
- `render(body_markdown, tenant)` → `RenderedEmail(html, plaintext_fallback)`

**Process:**
1. Convert body markdown to HTML paragraphs
2. Load `tenants/<name>/email_template.html` (Jinja-style)
3. Inject body, signature.html, brand color from config
4. Generate plaintext fallback (markdown → plain)

### `feedback/`
**Job:** Daily sweep that compares our drafts to what Dad actually sent, builds the trust/quality data.

**Interface:**
- `audit_recent_drafts()` → updates DB rows with outcome metrics

**Process:** for each draft created in last 24h, find corresponding sent message in Sent folder (matching thread + later timestamp), compute edit-distance, categorize as `sent-as-is | lightly-edited | heavily-rewritten | not-sent`, update DB.

This data feeds:
- The eventual daily digest email to Dad
- Decisions about which categories are safe enough for auto-send
- Voice-tuning iteration during PoC

### `pipeline.py`
**Job:** Orchestrator. Wires the components together. Owns the polling loop, the in-process lock, the error-handling discipline.

---

## Data flow (one inbound email)

```
1. Cron tick (every 60s)
   └─→ gmail_client.list_unprocessed_threads()

2. For each thread:
   ├─→ gmail_client.get_thread(id)
   ├─→ filters.should_skip(thread)
   │     if skip → label `processed-skipped`, done
   ├─→ knowledge.load("shine")    [cached]
   ├─→ classifier.classify(thread, kb)
   │     if not should_draft → label `processed-skipped` + log reason, done
   │     if sensitivity == "high" → label `flag-for-human`, NO DRAFT, done
   ├─→ drafter.generate(thread, kb, voice, classification)
   ├─→ renderer.render(body_markdown, "shine")
   ├─→ gmail_client.create_draft(thread_id, html, plaintext, in_reply_to=...)
   ├─→ db.save_draft_record(thread_id, draft_id, body, classification, kb_version)
   └─→ gmail_client.add_label(thread_id, "processed")

3. Daily sweep (separate cron, runs once at 6am):
   └─→ feedback.audit_recent_drafts()
```

**Source of truth for "did we handle this":** the `processed` Gmail label. Cheap, durable, survives crashes and redeploys, no risk of DB drifting from reality.

---

## Tenant data layout

```
tenants/
└── shine/
    ├── config.yaml         # brand color, contact info, signature display name
    ├── knowledge/
    │   ├── pricing.md
    │   ├── schedule.md
    │   ├── policies.md
    │   ├── faqs.md
    │   └── about.md
    ├── voice.md            # tone rules + 5-10 few-shot example replies
    ├── signature.html      # rendered into every email
    ├── email_template.html # Jinja: wraps {{body}} + {{signature}}
    └── logo.png            # inline-embedded in signature
```

---

## Tech stack

- **Language:** Python 3.12
- **Hosting:** Railway (always-on service, hobby plan)
- **Database:** Railway Postgres add-on
- **LLM:** Anthropic Claude Sonnet 4.6 (default) via official SDK; Opus 4.7 reserved for optional sensitivity-based escalation
- **Gmail API:** `google-api-python-client` with OAuth refresh token
- **Templating:** Jinja2 for HTML email
- **Config:** YAML per tenant, env vars for secrets
- **Local dev:** `.env` file (gitignored), test Gmail account
- **CI/CD:** Railway auto-deploy on push to `main` branch in GitHub

---

## Deployment

- Single Railway service running the polling loop and the daily sweep cron (or two services if simpler).
- Postgres add-on for state.
- Secrets in Railway environment variables: `GMAIL_REFRESH_TOKEN`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, `ALERT_EMAIL_TO`.
- Persistent volume for the `tenants/shine/` folder, OR just check it into the repo and deploy with the code (simpler; pick at implementation time based on whether we want non-engineers editing it).
- Spending cap on Railway set to ~$10/month as safety net.

**Estimated monthly cost:** ~$5–10 Railway + ~$10–20 Anthropic API at Shine's expected volume = **~$15–30/mo total** for the PoC + early production phase.

---

## Error handling (lean)

| Failure | Behavior |
|---|---|
| Gmail or Anthropic API transient (5xx, timeout) | Retry once with backoff. If still failing, label thread `draft-error`, move on. Next cron tick retries automatically. |
| Don't mark `processed` until draft created | The label is the source of truth; partial failures = pickup next tick. |
| Gmail auth revoked/expired | Loud alert email. Refuse to mark anything processed (so we don't drop emails). |
| KB files won't parse at startup | Refuse to start. Loud alert. Stale KB is worse than no service. |
| ≥5 draft errors in an hour | Throttled alert email. |
| Overlapping cron ticks (slow LLM call) | Simple in-process lock. Second tick skips, runs next minute. |

That's the entire error-handling design. Everything else (draft length checks, malformed-JSON-specific paths, multi-tier failure labels) is deferred until data shows it's needed.

---

## Observability

1. **Structured logs to Railway log stream.** Per-email journey: classification, decision, LLM tokens, latency, draft created (or why not).
2. **Postgres database as durable record.** Every draft, classification, KB version used, eventual outcome (post-feedback-sweep). Inspectable from any Postgres GUI.
3. **Alert email on real failures.** Auth revoked, KB unparseable, error rate spike. Threshold-gated to avoid spam.

---

## Testing

**Three layers, no more:**

1. **Unit tests** for pure logic only: rule filter, renderer, edit-distance calculator. No external deps.
2. **End-to-end integration tests against the test Gmail account.** ~10–15 hand-crafted golden emails covering: simple schedule question, pricing, follow-up in thread, complaint (no draft), spam-ish (skip), refund (flag), ambiguous, very short ("ok thanks"), weird formatting, reply where Dad already drafted (leave alone). Each has expected outcome (`drafted`/`skipped`/`flagged`); assert outcome plus eyeball draft body for tone.
3. **No mocks** for Gmail or Claude — those are exactly the surfaces most likely to break. Full real test run cost: ~$0.30. Cheap.

**Voice quality gate (manual):** before going live on Shine's real inbox, the developer (and Dad) read 10–20 sample drafts and give thumbs-up. Subjective quality is the real bar.

**Locked rule:** any change to prompts or `voice.md` re-runs the golden test suite.

---

## Voice and presentation

**Sign-off style:** intentionally vague responder (no specific person's name). Body uses first-person singular ("I checked the schedule and..."), sign-off is something like `— Shine Dance Fitness` or `Warmly, Shine` (workshopped in `voice.md`). Trade-off acknowledged: vague signers can read as bot, so the *body* must do extra work to feel personal — first-person voice, specific to the customer's actual question, warm.

**HTML formatting:** clean, not over-designed. Real `<p>` paragraph spacing, system fonts (no webfonts — clients strip them), single brand-color accent, small inline logo (~60–80px) in signature. Best small-business emails are well-written prose with a tasteful sig — not heavy banners or social-icon strips.

**Logo:** Shine's actual logo from their existing brand. **No AI-generated imagery** — it would clash with the rest of their brand and read "off."

**Signature contents:** business name + logo + address + phone + website + social. No specific person's name (per the vague-responder choice).

**Body output:** the LLM produces markdown, the renderer wraps it. Keeps the LLM focused on prose; signature consistency comes from a real template not regenerated text.

---

## Auto-send tiering (future)

Not built initially. **Architecture hook:** every classification produces structured `category` + `sensitivity` + `confidence`. Once we have weeks of feedback-loop data showing certain categories are sent unedited >95% of the time, a config flag flips that one category to auto-send. Sensitive categories (`complaint`, `refund`, `ambiguous`, anything `sensitivity != low`) stay draft-only forever, hardcoded.

For PoC and Shine launch: every draft → Drafts folder, period.

---

## Multi-tenant evolution (future, not built)

The design is positioned for it without paying for it now. The path:

1. Add `tenant_id` column to all DB tables.
2. Make `tenants/` a directory of N tenants, each with its own KB/voice/signature/config.
3. The pipeline iterates tenants, polling each one's Gmail.
4. Per-tenant Gmail credentials stored encrypted in DB (not env vars).
5. Add web admin for KB editing — and possibly Google Sheets sync for tabular content (schedule, pricing) since owners live in spreadsheets.

None of this requires touching `drafter/`, `classifier/`, `renderer/`, or `filters/` — the per-tenant boundary is clean.

---

## Out of scope (PoC)

- Web admin UI for KB editing
- Daily digest email to Dad (planned as the first add-on after PoC; architecture supports it via the `feedback/` data)
- Auto-send for any category
- Multi-tenant database / tenant onboarding flow
- RAG / vector search over KB
- Google Sheets / Notion integration
- Push-based Gmail notifications (Pub/Sub) — polling is fine for now
- A/B testing of prompts
- Analytics dashboard

Each of these has a clean integration point in the architecture if/when we add it.

---

## Success criteria

**PoC success (test Gmail account):**
- All 10–15 golden test emails get the expected outcome (drafted / skipped / flagged)
- Drafts read as human and on-brand to the developer's eye on a sample of 20+ real-style inputs
- System runs continuously on Railway for 48+ hours without intervention
- Per-email cost stays under $0.05

**Production launch readiness (Shine real inbox):**
- All PoC criteria met
- Dad reads 10–20 drafts on test account and gives thumbs-up to voice quality
- No drafts in sensitive categories (refund, complaint) — those reach the `flag-for-human` label correctly
- Failure-mode plan tested at least once (e.g., revoke and re-grant Gmail token to verify alert fires)

**Production health (after launch):**
- ≥70% of drafts get sent with light or no edits within 4 weeks
- Zero "embarrassing to send" drafts make it past Dad
- ≤2 alert emails per week (excluding genuinely unhealthy events)

---

## Open questions deferred to implementation

- Exact Jinja template structure for the email — design once we see what Shine's existing emails look like
- Polling interval — start at 60s, tune based on cost/latency tradeoff observed in production
- Whether `tenants/shine/` lives in the git repo or on the Railway volume (probably repo for PoC, volume later)
- Specific category taxonomy for the classifier — start with the categories listed and refine as we see real emails

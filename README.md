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

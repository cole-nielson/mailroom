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

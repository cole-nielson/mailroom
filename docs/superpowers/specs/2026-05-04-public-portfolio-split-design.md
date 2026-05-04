# Public Portfolio Split — Design Spec

**Date:** 2026-05-04
**Status:** Approved, ready for implementation planning
**Goal:** Separate the developer's private use of the project (with Shine tenant) from the public portfolio version (with a generic example tenant). Single repository, dual reality.

---

## Problem

The repository was developed using "Shine Dance Fitness" as the first tenant — content scraped from publicly available brand info on shinedancefitness.com. While the content itself isn't private, the developer wants the public-facing GitHub repository to:

1. Be **independent of any specific real client** — a true open-source portfolio piece
2. Allow **anyone visiting the repo** to clone it, plug in their own credentials, and run the system
3. Demonstrate the multi-tenant capability with a **generic, plausible example tenant**, not a specific real business
4. Preserve the **commit history** showing the project's evolution (including the Shine work) — that history is part of the portfolio story

The developer also wants their **local working tree** to continue housing the Shine tenant for their own use — but git should stop tracking it, and no future commits should include Shine content.

---

## Approach

**One repository, switch tenants going forward.** The repository pushes to GitHub with full history. From the next commit onward, `tenants/shine/` is no longer tracked; `tenants/example_roofer/` becomes the demo tenant.

Why one repo (not two): the developer explicitly wants the commit history visible on GitHub — it tells the story of the build. Separate repos would lose that. The Shine content in past commits is just publicly-available brand info, so leaving it in history is acceptable.

---

## Changes

### 1. Add `tenants/example_roofer/` (new tracked content)

A plausibly-real but fake roofing business. Content:

- **Business:** Apex Roofing & Exteriors
- **Location:** Asheville, NC (real city, fake business)
- **Founding story:** family-owned, two generations, 25 years
- **Services:** inspections, repairs, replacements, gutters, storm-damage insurance claim help
- **Voice:** warm, plain-spoken, no-BS — explicitly NOT salesy
- **Brand color:** dark slate or earth tone (not pink — visually distinct from Shine for portfolio polish)

Files matching the existing `tenants/<name>/` shape:

- `config.yaml` — display_name, brand_color, website, email, address, phone, reply_signoff
- `voice.md` — tone rules + 4–6 few-shot examples appropriate for the trade
- `knowledge/about.md` — business background, founders, philosophy
- `knowledge/services.md` — service offerings with descriptions
- `knowledge/pricing.md` — rough pricing ranges, free estimates, financing
- `knowledge/insurance_claims.md` — process for storm-damage claim help
- `knowledge/policies.md` — warranty, scheduling, payment, refunds
- `knowledge/faqs.md` — common customer questions
- `signature.html` — same Jinja template shape as Shine (logo + brand-color line + contacts + socials)
- `email_template.html` — outer HTML wrapper
- `logo.png` — placeholder (1×1 transparent or simple text mark)

### 2. Remove Shine from tracked files

```
git rm -r tenants/shine/
```

This stages the deletion. The folder remains in the local filesystem (git rm without `--cached` actually removes the working copy too, so we use `git rm --cached -r tenants/shine/` instead, which only untracks).

Then add to `.gitignore`:
```
tenants/shine/
```

### 3. Update default tenant references

Change defaults from `shine` to `example_roofer` in:
- `main.py` (`tenant_name = os.getenv("TENANT_NAME", "example_roofer")`)
- `tests/integration/golden/test_golden_emails.py` (`tenant = os.getenv("TENANT_NAME", "example_roofer")`)
- `.env.example` (`TENANT_NAME=example_roofer`)

### 4. Rewrite `README.md` for open-source/portfolio framing

Reframe the README around three audiences:

- **Visitors** wanting to understand what the project does (lead with problem + solution)
- **Engineers** evaluating the codebase (architecture, design decisions, tech stack)
- **Anyone** who wants to deploy their own instance (clear setup steps using `example_roofer` as the worked example)

Remove any "first production tenant launching" language that implies a specific real customer. Add a "Try It Yourself" section explaining: clone, set up Anthropic + Gmail credentials, deploy to Railway (or anywhere), and add your own tenant folder. Mention the Python package is named `shine_email_assistant` for legacy reasons (the project's first tenant) — cosmetic only.

### 5. What does NOT change

- **Python package name** stays `shine_email_assistant` (renaming touches every import — disruptive, no real benefit)
- **Tenant architecture, classifier, drafter, all code** — already tenant-agnostic
- **Existing Railway deployment** — the developer's private playground, no changes from the public repo
- **`tenants/shine/` in past commits** — acceptable, content is public brand info
- **Local working tree** — keeps `tenants/shine/` (now untracked); developer can still work with it

---

## Non-Goals

- **Not** rewriting git history. Past commits with Shine remain.
- **Not** renaming the Python package or restructuring the codebase.
- **Not** updating the deployed Railway instance. The developer's deploy stays as-is for their personal use.
- **Not** adding multi-tenant runtime support (the architecture is already there; we're just demonstrating it via a second tenant on disk).

---

## Success Criteria

- [ ] `tenants/example_roofer/` exists with all expected content files
- [ ] `tenants/shine/` is no longer in `git status` (gitignored)
- [ ] `tenants/shine/` still exists in the local filesystem (untracked, usable for developer's private work)
- [ ] All 22 unit tests still pass
- [ ] `uv run python -c "from shine_email_assistant.knowledge import KnowledgeLoader; from pathlib import Path; print(KnowledgeLoader(Path('tenants')).load('example_roofer').version)"` succeeds — confirms the new tenant loads
- [ ] README reads as a portfolio piece, not a Shine-specific build doc
- [ ] Default `TENANT_NAME` is `example_roofer` everywhere
- [ ] Repo is pushed to GitHub at `github.com/cole-nielson/mailroom` (or the user's chosen name)
- [ ] GitHub default branch is `main`, includes full commit history

---

## Open Questions

- **Repo name:** "mailroom" was the working name from the prior README rewrite. Confirm before push.
- **Optional polish:** generate a slightly nicer placeholder logo for the example roofer (procedural / text-based) — low priority.

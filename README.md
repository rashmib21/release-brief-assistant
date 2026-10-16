# Release Brief Assistant

A web app where a developer enters a structured release package (features, bug fixes, changed behaviour, QA summary, known limitations, migration notes, affected user groups) and gets AI-drafted release summaries for two audiences. The AI drafts; a person reviews, edits, approves or rejects every statement. The AI never approves a release and never deploys anything.

- Live app: `<add the hosted URL>`
- Stack: FastAPI, SQLAlchemy, Postgres (SQLite locally), Gemini (`google-genai`), React + TypeScript + Vite
- Try it fast: open the app and press **Load sample release**.

## What it does

1. **Package form.** Seven sections. Every item gets an ID (`F1` feature, `B1` bug fix, `C1` changed behaviour, `Q1` QA, `L1` limitation, `M1` migration, `U1` user group). QA items can say which features or fixes they cover.
2. **Deterministic section check (no AI).** A blank section is an error. An explicit `None` / `N/A` passes. Duplicate IDs and QA links to unknown items are errors. Features with no linked QA get a warning. The AI analysis is blocked until the check passes.
3. **AI analysis (3 steps).**
   - Classify each change by user impact (high/medium/low), affected user groups and a reason.
   - Find missing release information and claims that the QA evidence does not support (for example "works on all devices" when QA only covered Android).
   - Write summaries for **internal technical users** and **non-technical stakeholders/clients**. Every statement cites the release items or QA items behind it, and each audience gets a "Known risks and limitations" section.
4. **Guardrails on AI output (deterministic).** Cited IDs must exist, every statement needs a citation, both audiences need a risks statement. On failure the step is retried once with the problems fed back; if it still fails the user sees an error with a retry button and nothing is saved. A statement that cites a feature/fix/behaviour change but no QA item is flagged as unsupported by plain code, independent of the AI.
5. **Human review.** Each statement can be edited, approved, rejected or reset. AI output is always saved as `draft`. Only a user action can set `approved`.
6. **Versions.** The package of a saved version is immutable once it has been analysed. Changing it means saving a new version. Version 2 carries over version 1's statements.
7. **Stale statements.** Each citation stores a hash of the cited item at the time of writing. If that item changes or is removed in a new version, statements citing it become `stale` with the reason ("F1 changed", "B1 was removed"). Unrelated approvals survive. A stale statement is resolved by editing and approving it (which re-confirms it against the new evidence), or by rejecting it.
8. **Compare.** Pick two versions to see added, removed and changed items per section, plus the statements from the older version that would be stale in the newer one.
9. **Final reviewed brief.** Available only when no statement is draft or stale and at least one is approved. It contains the approved statements (your edited wording wins), the open flags (missing info, unsupported claims) and a disclaimer that it is not a release approval. Generating it locks the version. Export is Markdown (copy or download).

## Architecture

```
frontend/ (React)  --/api-->  backend/ (FastAPI)  --> Postgres / SQLite
                                   |
                                   +--> Gemini (JSON output, validated by pydantic + guardrails)
```

One service: FastAPI serves the API under `/api` and the built React app at `/`, so there is no CORS setup and only one thing to deploy.

```
backend/app/
  main.py            app, request-ID logging middleware, static serving
  routers/           releases (versions, compare), versions (validate, analyze, brief), statements (review)
  services/
    package.py       IDs, normalising, item hashes, QA coverage
    validation.py    deterministic section checks
    guardrails.py    checks on AI output + unsupported-claim flag
    diffing.py       version diff and stale detection
    ai_workflow.py   3 AI steps, retry, ai_runs logging
    brief.py         final brief
    ratelimit.py     in-memory limiter for the analyze endpoint
  llm/               Gemini client, prompts, deterministic mock provider
  models.py          releases, release_versions, analyses, statements, ai_runs, final_briefs
```

Data model: `release_versions.package_json` (immutable package) and `item_hashes_json`; `statements.citations_json` stores `[{id, hash}]`; `ai_runs` has one row per AI call (step, model, prompt hash, latency, status, error).

### Logging

- App logs: one JSON object per line on stdout, with a request ID on every line (also returned as the `x-request-id` header).
- AI-workflow logs: each AI call is logged (`ai_step`) and stored in the `ai_runs` table, including guardrail failures and provider errors.

### Responsible AI use

- The AI has no tools and no write access. It returns JSON that code validates; only code writes to the database.
- Package text is untrusted: it is wrapped in tags and the system prompt tells the model to treat it as data, not instructions.
- No endpoint deploys anything or approves a release. Version states are `draft`, `in_review`, `brief_generated`.
- Provider errors (rate limit, timeout, bad output) become clear error states with a retry button.

## Run locally

Backend (Python 3.12+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env        # set GEMINI_API_KEY, or set LLM_PROVIDER=mock for offline use
uvicorn app.main:app --reload  # http://localhost:8000
```

Frontend (Node 20+), in another terminal:

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173, proxies /api to :8000
```

Production-style single service: `npm run build` in `frontend/`, then start the backend; it serves `frontend/dist`.

## Tests

```bash
cd backend && pytest -q        # 59 tests
cd frontend && npm test        # 7 tests
```

End-to-end smoke test on the built-in sample release, against any running instance (local or deployed). It checks the whole workflow through the API (section check, AI analysis, review gating, stale detection on a new version, compare, final brief) and prints AI-quality observations as warnings:

```bash
python scripts/smoke_test.py --base-url http://localhost:8000
```

Backend tests use the mock LLM provider and a temporary SQLite database. They cover: required-section checks (blank vs `None`), guardrails (fake citation, missing citation, missing risks), unsupported-claim flagging, AI output never being approved, retry-then-succeed and persistent-failure paths, provider rate-limit errors, analyze rate limiting, edit/approve/reject rules, final-brief gating and locking, stale detection (changed and removed items, unrelated approvals surviving), resolving stale statements, and version comparison.

## Deployment

Docker, single service (`Dockerfile` builds the React app, then runs FastAPI).

1. Create a hosted Postgres database (for example Neon) and copy its connection string.
2. Create a web service from this repo using the Dockerfile (for example on Render).
3. Set environment variables: `DATABASE_URL`, `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL`.
4. Open `/api/health`, then use **Load sample release** to check the flow end to end.

Tables are created on startup (`create_all`); if the database is still waking up, startup retries for about 30 seconds. `postgres://` and `postgresql://` URLs are both accepted (the app uses the psycopg2 driver). Dependencies in `backend/requirements.txt` are pinned to tested versions. Free hosting tiers may sleep when idle, so the first request after a pause can take a while.

## Scope

Completed: everything listed under "What it does".

Intentionally left out: Git integration, real deployment, automated rollback, public changelog publishing, user accounts, PDF export, regenerating a single statement (re-running the analysis replaces all statements of a version and asks for confirmation if any are approved).

## Known limitations

- No authentication: anyone with the URL can use the app. The analyze endpoint is rate limited per IP (in memory, single instance) to protect the API key.
- The AI's judgement of "unsupported claims" is only as good as the model; the deterministic QA-citation flag is a safety net, not a proof. Linking QA items to the items they cover improves accuracy.
- Stale detection compares item text and QA links by hash. A cosmetic edit to an item also makes its statements stale; that is deliberate (a person should re-check).
- No database migrations tool; schema changes need a manual migration or a fresh database.
- The Gemini provider needs a valid API key and is subject to its quota. The mock provider exists for tests and offline demos only.

# Agent usage

## Tools

- Claude (Anthropic, Sonnet 5.5) in the Claude app with code execution: planning, code generation, running tests, writing docs.
- Gemini API inside the product itself (see README). That is a runtime dependency of the app, not a development tool.

## How the work was split

I chose the problem, the stack (FastAPI + React) and the scope limits, and I asked for the design to be re-checked against the assignment instructions before any code was written. The agent produced the code and tests in steps: backend, then tests, then frontend, then docs. I am responsible for everything submitted and can explain it.

Delegated to the agent: data model and API, deterministic validation, guardrails, stale detection and diffing, prompts, the mock LLM provider, React pages, the Dockerfile, tests, README.

Kept human: choice of problem and stack, what to cut from scope, review of the agent's plan against the instructions, deployment accounts and API keys, final end-to-end check on the hosted app.

## Representative prompts

1. "Explain both problem statements at a beginner level and what the flow is, according to the instructions."
2. "I'm choosing task one, with FastAPI and React. Give me the full flow of the application with the tech stack."
3. "Recheck the structure you gave and, if anything differs from the instructions, change it."
4. "Proceed to implementation, and also write a document of the whole approach so another account can continue if tokens run out."

## Important agent mistakes and rejected suggestions

- **Release-level "reviewed" status.** The first design had a release status that could read like a release approval. The assignment forbids the AI marking a release approved, so this was replaced by a per-version `review_state` (`draft`, `in_review`, `brief_generated`) and a disclaimer in the brief.
- **Two hosts (Render + Vercel) and CORS.** Replaced by one service where FastAPI serves the built React app, to remove a failure point on the hosted deployment.
- **PDF export and "regenerate stale" endpoint.** Dropped: the instructions say extra features do not improve the score, and they add surface area.
- **Unsupported claims left to the AI alone.** Rejected as too weak. Added a deterministic flag (statement cites a feature/fix/behaviour change with no QA citation) and QA-to-item links.
- **Stale detection was under-specified.** The first plan did not say where version 2's statements come from. Fixed: statements are copied forward with citation hashes, then compared against the new package.
- **Test bug.** A test listed `app.routes` to prove there is no deploy endpoint; with the installed FastAPI the router entries have no `path`, so the test crashed. Changed to read the OpenAPI schema instead.
- **Stale statements were invisible on a new version.** The backend copies statements into version 2 and marks stale ones, but the review page only showed statements when the version had its own analysis row, which a new version does not. The 32 backend tests passed because they check the API, not the screen. Found by driving the UI in a real browser (Chromium) when a script timed out waiting for the statements. Fixed: the page now shows carried-over statements, explains that the version has no analysis of its own, and offers to re-run it.
- **Two screens disagreed on stale counts.** The compare page counted a rejected statement as stale while the new version page kept it rejected. Found by the end-to-end smoke test (`scripts/smoke_test.py`) on the sample data; fixed and covered by a regression test.
- **Redesign left unfinished.** A first frontend redesign (new styles, stepper, new Releases pages) was started and not finished, which left the other pages unstyled. I read the existing design direction instead of replacing it, and migrated the remaining pages to it.
- **Mock LLM text.** Statements read "orders.. QA verified." because the mock appended a full stop to text that already had one. Fixed in the mock; it does not affect the Gemini path.
- **TypeScript config.** `Array.prototype.at` failed to compile because the target was ES2020; raised to ES2022.

## How output was verified

- Backend: 33 pytest tests (validation, guardrails, workflow retries and failures, review rules, final-brief gating, stale detection, compare). All pass.
- Frontend: `tsc --noEmit` type check and production build succeed; 4 vitest tests pass.
- UI: the whole flow was driven in headless Chromium against the mock provider (sample release, analysis, evidence panel, approve all, new version with stale statements, compare, final brief, and a 390px-wide mobile view). No console errors and no horizontal overflow on mobile. Screenshots were reviewed by the agent; I should repeat the walkthrough myself on the hosted app.
- Smoke test of the single-service setup: `/api/health`, the React app at `/`, client-side routes, static assets and unknown API paths return the expected responses.
- Prompts and guardrails were read by me; the guardrails are plain code, so the AI's citations are never trusted without checking.
- Not verified by the agent in its sandbox: live Gemini calls (no API key there; tests use the mock provider), the Docker build, and the hosted deployment. These were checked by me on the deployed app (fill in the date and what you checked).

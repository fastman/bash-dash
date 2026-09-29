<!-- PLAN-REVIEW-REPORT -->
# Plan Review: First Sandboxed Command Implementation Plan

- **Plan**: context/changes/first-sandboxed-command/plan.md
- **Mode**: Deep (claims verified inline against code, installed Django 6.1 / docker-py sources, catalog data)
- **Date**: 2026-09-29
- **Verdict**: REVISE → SOUND after triage (all findings fixed in plan)
- **Findings**: 0 critical, 4 warnings, 4 observations

Triage note: this review ran unattended (no interactive channel to the user). Every finding was clear-cut and was triaged by the reviewer. The fixes were applied to `plan.md`, and to `plan-brief.md` where affected. None of the findings needed a human decision. As instructed, the review did not reopen the two decisions the user had already confirmed: the English UI, and not counting our-side failures while counting timeouts and wrong answers.

## Verdicts

| Dimension | Verdict (before triage) |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

The plan's claims match the code and the installed libraries:

- **Paths**: 10/10 exist, including every file the plan modifies: `challenges/sandbox.py`, `challenges/catalog.py`, `config/settings.py`, `config/urls.py`, `.gitignore` and `challenges/tests/test_sandbox.py`.
- **Symbols**: 9/9 found:
  - `run_command`, `reap_stale`, `_get_client` and `SandboxResult.error_internal`
  - `FakeImages.requested` (`fakes.py:67`)
  - docker-py `from_env(max_pool_size=…)` (`client.py:98`)
  - Django 6.1 SQLite `transaction_mode` and the `;`-split `init_command` (`base.py:181-212`)
  - both named tests at `test_sandbox.py:149` and `:203`
  - `verify_challenges` `reap_stale()` at `:207`
- **Data claims**: 42 playable challenges, starting `hello_world` → `current_working_directory`, and 0 descriptions or titles containing `<`.
- **Brief↔plan**: consistent, except that the brief still labelled the user-confirmed decisions as unconfirmed (F8).
- **Stale references**: 7 line numbers in the plan pointed at the wrong lines (F6).
- **Progress↔Phase**: consistent. All 4 phases match, there are 28 rows, and no checkboxes appear outside Progress.

## Findings

### F1 — `ALLOWED_HOSTS` env hook is promised but never built

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 Manual Verification (phone over LAN); Phase 1 §2
- **Detail**: Phase 4's real-phone check needs `runserver 0.0.0.0:8000` with "`ALLOWED_HOSTS` via env for dev only". But `config/settings.py:29` has `ALLOWED_HOSTS = []`, and no phase adds an env hook. With `DEBUG=True` and an empty list, Django accepts only localhost, so a request to the LAN IP gets a 400 (DisallowedHost).
- **Fix**: Phase 1 §2 adds `ALLOWED_HOSTS` from `BASHDASH_ALLOWED_HOSTS`, comma-split, default empty. The Phase 4 manual step now shows the exact command.
- **Decision**: FIXED

### F2 — Phase 4 benchmark runs describe two identical configurations

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 §2 — Verification record
- **Detail**: The plan asks for runs made "once unpinned and once with `BASHDASH_SANDBOX_CONCURRENCY` left at 8". Those two variants cannot differ:
  - The default cap is already 8.
  - "Unpinned" is F-01's `--host-cpus` cpuset pinning (`verify_challenges.py:205,221`), which works through `run_command(host_overrides=…)`.
  - `bench_game` drives `game.services`, which never passes `host_overrides`, so it cannot pin.

  The implementer would have to guess what the second run was meant to measure.
- **Fix**: The runs are now `--players 15` (typical and with-abuse) and `--players 30` (typical), all at cap 8 and explicitly unpinned. The plan points to the F-02 event-VM re-run for real-CPU numbers. It does not leak the harness-only `host_overrides` into the game service.
- **Decision**: FIXED

### F3 — `submit_command` step order leaves the pre-checks, semaphore release and testability implicit

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 2 §2 — Service module ("Order inside `submit_command`")
- **Detail**: The step list has three gaps:
  - It does not say where the `finished`, `empty` and `too_long` checks happen. Placed after step 2 or 3, they would touch Docker or take a semaphore slot for commands that never run.
  - Step 5 "Release" is a plain step, not a `finally`. `run_command` raises `SandboxUnavailable` *after* acquire (`sandbox.py:186-194`), so a literal implementation leaks a slot on every Docker outage. After 8 outages the process would answer "busy" forever.
  - A module-level `BoundedSemaphore(settings.SANDBOX_MAX_CONCURRENT)` is sized at import. `override_settings` in the "busy" test then has no effect.
- **Fix**: Make the order explicit:
  1. Pre-checks come first, in the order finished → empty → too_long, using `sandbox.MAX_COMMAND_CHARS`.
  2. Then `reap_stale_once`.
  3. Acquire with `SANDBOX_QUEUE_TIMEOUT_S`; failure returns `busy`.
  4. Run `run_command` in `try/finally: release()`.

  The semaphore is built lazily by `_get_semaphore()`, and `_reset_semaphore()` exists for tests. A new test asserts that the slot is released on `SandboxUnavailable`.
  - Strength: prevents a slot leak that would turn a brief Docker hiccup into a permanent "busy" state for that process.
  - Tradeoff: two small helper functions.
  - Confidence: HIGH. The exception path is visible in `sandbox.py:186-194`.
  - Blind spot: none significant.
- **Decision**: FIXED

### F4 — A cut last challenge leaves a game with no challenge that is still "active"

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 §2 — `current_challenge`
- **Detail**: When `current_slug` was cut mid-event, `current_challenge` persists `next_playable(slug)`. If the cut slug was the last one, the result is `None`, but the contract does not set `finished_at`. `is_finished` is `finished_at is not None`, so the game would count as active while `current_challenge` returns `None`. `/play` would then have nothing to render, and the views would not redirect to `/done`.
- **Fix**: In that case, persist `current_slug=None` together with `finished_at=now` in one conditional update, without incrementing `solved`. The existing cut-mid-game test now also covers the case where the last slug is cut.
- **Decision**: FIXED

### F5 — The harness reaper can still kill live game containers

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 §1 / Phase 4 §2
- **Detail**: Carry-over (a) is fixed for the game, which uses `min_age_s=30`. But `verify_challenges` deliberately keeps `min_age_s=0` (`verify_challenges.py:207`). F-02 plans to re-run the harness on the event VM, and running it there while games are live would delete in-flight game containers, producing `internal` errors for players.
- **Fix**: The F-02 contract in `verification.md` now records "don't run `verify_challenges` on the event host while games are live". The brief's risks list says the same.
- **Decision**: FIXED

### F6 — Stale line references to F-01 code

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis, Key Discoveries, References
- **Detail**: F-01's review fixes shifted the code, so the plan cited these lines:
  - `sandbox.py:136-193` (now 155-218)
  - `:196-213` (now 228-245)
  - `:73-81` (now 76-85)
  - `:153` (now 179)
  - `:136-213` (now 155-245)
  - `catalog.py:74-88` (now 68-88)
  - `settings.py:75` (now 77)
- **Fix**: All references are updated to the current lines.
- **Decision**: FIXED

### F7 — The JS keeps the command for a retry on 503 but not on 500

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 §2 — `play.js`
- **Detail**: An `internal` error (500) is shown to the player as "internal error, try again" and is not counted, just like a 503. But `play.js` kept the command in the input only on a network error or a 503, so on a 500 the player would have to retype it.
- **Fix**: The command is now kept on a network error, an abort, a 503 or a 500.
- **Decision**: FIXED

### F8 — Plan and brief still marked the user-confirmed decisions as unconfirmed

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: plan.md decision-table preamble; plan-brief.md Key Decisions and Open Risks
- **Detail**: The user has confirmed the English UI and the counting rule (our-side failures don't count; timeouts and wrong answers do). Both documents still said "the user has not confirmed them" and listed English as an assumption.
- **Fix**: Both documents now mark these two decisions as user-confirmed. The other rows stay labelled as planner defaults.
- **Decision**: FIXED

## Triage summary

| Outcome | Findings |
| --- | --- |
| Fixed | F1, F2, F3, F4, F5, F6, F7, F8 (8) |
| Skipped / Accepted / Dismissed | none |
| Needs human decision | none |

Verdict after fixes: **REVISE → SOUND**. The approach holds up well:

- It adds no pattern the codebase already has an equivalent for.
- Each carry-over is fixed at the right layer.
- No DB transaction stays open during a sandbox run.
- The semaphore sits in the game layer, so the harness keeps its own parallelism.

The remaining planner defaults (app layout, session identity, `current_slug`, semaphore cap 8, 30 s reap age, JSON + vanilla JS) are sound as written. They are still open to the user overturning them.

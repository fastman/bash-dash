<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: First Sandboxed Command

- **Plan**: context/changes/first-sandboxed-command/plan.md
- **Scope**: Phases 1–4 of 4 (full plan, commits 8ab3a0f..b4e6815)
- **Date**: 2026-09-29
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Evidence summary

### Plan adherence

- Every planned change is present. There are no MISSING items and no meaningful DRIFT.
- Two trivial deviations, both fine:
  - Pool size is asserted in a new test, `test_client_pool_is_sized_to_concurrency_cap`, instead of by extending `test_client_is_created_lazily_and_cached`.
  - `verdict()` checks `timed_out` before `error`. This has no effect, because timeouts carry no player error.

### Success criteria, re-run during the review

- `manage.py test`: 102 tests, OK.
- `manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes.
- `migrate`: nothing to apply.
- `PRAGMA journal_mode` → `('wal',)`.
- `verify_challenges --only hello_world --skip-abuse` exits 0, with 0 leaked containers.
- `bench_game --players 15` exits 0. p50 0.546 s, p95 0.637 s, 0 lock errors, 0 leaked containers.
- `bench_game --players 15 --mix with-abuse` exits 0.
  - Non-abusers: p95 0.646 s.
  - Abuser: p50 5.18 s.
  - 0 lock errors, 0 leaked containers.
- `docker ps -aq --filter label=bash-dash.sandbox` is empty.

### Manual checks

- 3.6, 3.9, 3.10 and 4.6 are pending and need a human with a browser or phone. That is expected.
- 3.7 and 3.8 are ticked on server-side evidence: live `runserver` calls from the shell, recorded in verification.md. That is acceptable, but no browser was used.

### Security checks that passed

- **XSS**: `render_description` escapes first. play.js uses `textContent` for all output, and `innerHTML` only for server-escaped description HTML.
- **CSRF**: in place on both POST routes.
- **Session**: the UUID game id is server-side, so a player cannot reach another player's game.
- **Admin**: fully read-only.
- **Transactions**: no transaction is held across the sandbox run.
- **Double submit**: the `current_slug` guard advances a duplicate correct submit only once.
- **Semaphore**: released in `finally` on every path.
- **bench_game cleanup**: deletes only the games it created, by pk.

## Findings

### F1 — Docker failures surface as an HTML 500 instead of JSON 503 "sandbox unavailable"

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:208 (also `reap_stale_once` at :289, game/services.py:115-117)
- **Detail**: Two failure paths reach the player as a 500:
  - **Docker down when the process starts.** `client = client or _get_client()` runs outside the `try` that maps Docker errors to `SandboxUnavailable`. `reap_stale_once` swallows its own failure, then `run_command` calls `docker.from_env` again, gets an uncaught `DockerException`, and returns 500 HTML.
  - **Daemon lost after the client exists.** docker-py raises an unwrapped `requests.exceptions.ConnectionError`, which gets past both `except DockerException` clauses.

  The sub-agent reproduced both. In each case the player sees "Server error (500)", not the planned "Sandbox unavailable, try again", and with `DEBUG=True` the 500 page includes a traceback. The semaphore is still released. This contradicts manual check 3.10 ("Stop Docker … shows sandbox unavailable").
- **Fix**:
  - Move `_get_client()` inside the create `try` in `run_command`.
  - Add `requests.exceptions.RequestException` to the `except` around `_ensure_image`/`create` (→ `SandboxUnavailable`) and to `reap_stale_once`.
  - Add tests for both paths.
- **Decision**: FIXED (9350274, a04c7d2) — `_get_client()` moved inside the try; `RequestException` is mapped to `SandboxUnavailable` in `run_command` and caught in `reap_stale_once`; covered by unit tests plus a view test asserting a JSON 503 with nothing counted.

### F2 — Attempt rows and GameSession.attempts can disagree after the game finishes

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: game/services.py:132-148 (`_record`)
- **Detail**: `Attempt.objects.create` always runs, but the counter update is guarded by `finished_at__isnull=True`.
  - A run that overlaps the game finishing stores an Attempt row but does not increment `attempts`, and the response is still 200 `ran`. Examples: two correct submits on the last challenge from two tabs, or, in S-02, the time limit expiring mid-run.
  - The sub-agent reproduced it: 1 Attempt row, `attempts=0`.
  - S-03 ranking reads the counter, while admin and staff tooling read the rows. This follows the plan's literal contract, but the plan never said which of the two is the source of truth.
- **Fix A ⭐ Recommended**: Run the guarded counter update first, create the Attempt only if `rowcount == 1`, and otherwise return `FINISHED` (not counted).
  - Strength: The rows and the counter always agree. This matches S-02's "commands after time don't count" rule, which will reuse the same guard.
  - Tradeoff: A player whose command was already running when the game ended gets 409 "finished" instead of the output. That case is rare.
  - Confidence: HIGH — a small change inside one atomic block. Tests pin the rule.
  - Blind spot: The JS for a 409 on a still-open play page is untested. It should navigate to /done.
- **Fix B**: Drop the `finished_at__isnull` guard so every stored Attempt is counted.
  - Strength: A one-line change, and the player always sees their output.
  - Tradeoff: Attempts can grow after `finished_at`. S-02 would then need its own cut-off anyway.
  - Confidence: MED — this conflicts with where S-02 is heading.
  - Blind spot: How S-03 ranks games whose counters grew after `finished_at`.
- **Decision**: FIXED via Fix A (af89c55) — the guarded counter update runs first and gates the Attempt insert; a run overlapping the finish returns `finished`; a test covers the overlap.

### F3 — Unplanned additions not recorded in the plan

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: game/views.py:118-125, 36-45, 151-152
- **Detail**: Benign additions beyond the plan:
  - 400 `bad_request` for a malformed JSON body (acknowledged by the implementer).
  - "Incorrect." for a wrong answer with no error text (acknowledged).
  - A top-level `message` on every JSON response.
  - A 403 `no_game` body without counters.
  - `/done` redirects an active game to `/play`.
  - A client-side blank-command check.
  - The last command is shown on the play page.
  - Admin `search_fields`.
  - `game/tests/test_bench.py`.

  All of these are sensible. The plan is the ground truth for S-02 and S-03, and it doesn't mention them.
- **Fix**: Add a short "Implementation addenda" note to plan.md listing these.
- **Decision**: FIXED (this docs commit) — "Implementation Addenda" section added to plan.md.

### F4 — Deeply nested JSON body returns 500

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/views.py:120-124
- **Detail**: `json.loads` on `'[' * 200000` raises `RecursionError`, which the `except (ValueError, KeyError, TypeError)` does not catch, so the server returns 500. Every other malformed body tried returns 400: a list, a string, null, a number, a non-string command, invalid JSON, and invalid UTF-8.
- **Fix**: Reject `len(request.body) > 4096` with 400 before parsing. A valid body is at most about 1.2 KB. Alternatively, add `RecursionError` to the `except`.
- **Decision**: FIXED (a04c7d2) — bodies over 4 KB get a JSON 413 before parsing; `RecursionError` is also caught (400); tested.

### F5 — Lone surrogate in a command is reported as "Command too long"

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:209, game/services.py:117
- **Detail**: `{"command": "echo \ud800"}` makes `command.encode()` raise `UnicodeEncodeError`, a `ValueError` subclass. The service's length backstop catches it and returns 400 `too_long`. Nothing crashes and nothing is stored, but the message is wrong.
- **Fix**: In the view, reject commands that don't encode as UTF-8 with 400 `bad_request` (`command.encode()` in the existing try).
- **Decision**: FIXED (a04c7d2) — a command that is not UTF-8 encodable gets 400 `bad_request` in the view; tested.

### F6 — reap_stale_once holds a process-wide lock across an unbounded Docker call

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:289-303
- **Detail**: Until the first reap succeeds, every submit waits on `_reap_lock` before the semaphore, and that wait has no timeout. If the daemon hangs (docker-py's default timeout is 60 s), requests pile up past `SANDBOX_QUEUE_TIMEOUT_S` and past play.js's 25 s abort. The lock is only held on the first call per process, or until a reap succeeds, so the exposure is small.
- **Fix**: Use `_reap_lock.acquire(blocking=False)`, so concurrent callers skip the reap while one is in progress.
- **Decision**: FIXED (9350274) — non-blocking `_reap_lock.acquire`; a concurrent caller skips without marking the reap done; tested.

### F7 — Game tests import helpers from other test modules instead of a fakes module

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/tests/test_views.py:12, game/tests/test_bench.py:11, game/tests/test_services.py:7
- **Detail**: `challenges/tests/` keeps its shared doubles in `fakes.py`. The game tests instead import `result` from `game/tests/test_services.py` and the private `_write_excluded` from `challenges/tests/test_catalog.py`. Only functions are imported, so no test runs twice, but the private coupling across test modules is brittle.
- **Fix**: Move `result` to `game/tests/fakes.py` and `_write_excluded` to `challenges/tests/fakes.py` (renamed `write_excluded`).
- **Decision**: FIXED (07402c2) — `result` moved to `game/tests/fakes.py`, `write_excluded` to `challenges/tests/fakes.py`.

## Triage summary

The user chose to fix all findings.

| Outcome | Findings | Count |
|---|---|---|
| Fixed | F1, F2 (Fix A), F3, F4, F5, F6, F7 | 7 |

After the fixes:
- `manage.py test`: 113 tests OK.
- `check`: clean.
- `makemigrations --check`: no changes.
- `bench_game --players 15`: exit 0, p95 0.642 s, 0 lock errors, 0 leaked containers.

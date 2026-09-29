# First Sandboxed Command — Plan Brief

> Full plan: `context/changes/first-sandboxed-command/plan.md`

## What & Why

This is roadmap slice S-01, the north star. A player reads the rules, enters a nick, clicks Start and solves main-set challenges in a fixed order by typing bash commands. Each command runs in F-01's hardened sandbox. The player sees the output and a correct/incorrect verdict, and every run counts as an attempt. Without this there is no product. The slice is also the biggest technical unknown: integration, and latency under concurrent players.

## Starting Point

F-01 delivered `challenges.sandbox.run_command()`, which always returns a verdict and always cleans up, and `challenges.catalog.main_set()` (42 playable challenges, no cuts). The app has no models, views or player pages yet. F-01's review left four carry-overs:

- (a) `reap_stale` can delete another worker's in-flight container.
- (b) docker-py's connection pool is capped at 10.
- (c) `images.get` runs on every command.
- (d) `catalog.get` also returns excluded challenges.

## Desired End State

On a phone-width browser, `/` shows the rules and a nick form. `/play` shows challenge N of 42 with a command box, and submitting shows the output and verdict without a page reload. A correct answer advances to the next challenge. A reload returns to the same game with the same counters and the last output. Finishing all challenges shows a minimal done page. Carry-overs (a)–(d) are fixed and tested. `bench_game --players 15` gives measured latency, recorded in `verification.md`.

## Key Decisions Made

This planning session ran unattended, so each row below is the planner's recommended default, grounded in the codebase. The user has not confirmed them and can overturn any of them.

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| App layout | New `game` app; `challenges` stays infrastructure | Keeps sandbox/catalog reusable by the harness and gameplay rules in one testable place | Plan |
| Player identity | `game_id` in the Django session cookie | No accounts (PRD); gives reload-safety for free, and S-02 builds on it | Plan |
| Progress pointer | `current_slug`, resolved only through `main_set()` lookups | Fixes carry-over (d); a mid-event cut can't shift players onto the wrong challenge | Roadmap carry-over |
| Attempt record | `Attempt` row per run + counters on `GameSession` | Restores last output on reload; gives S-03 the ranking inputs (`last_solved_at`) | Plan |
| What counts | Every run with a verdict (incl. timeouts); not counted: too long, empty, sandbox down, busy, `error_internal` | Players aren't charged for our failures; `ls`/`cat` still count (PRD) | PRD + Plan |
| Double submit | Conditional `UPDATE … WHERE current_slug=…` + `F()` counters | A correct answer advances exactly once without row locks (SQLite) | Plan |
| Concurrency | Per-process semaphore, default 8, 10 s queue then "busy"; docker pool = cap + 2 | Fixes carry-over (b); 8 is inside F-01's measured envelope (~0.3 s p95) | Roadmap carry-over + F-01 data |
| Reaping | `reap_stale(min_age_s=30)`, lazily once per process, never in `AppConfig.ready()` | Fixes carry-over (a) and is safe from any worker; `ready()` would hit Docker on `migrate`/`test` | Roadmap carry-over |
| Image check | Cache positive `images.get` per client; invalidate on `ImageNotFound` | Fixes carry-over (c): one fewer Docker round trip per command | Roadmap carry-over |
| SQLite | WAL + `transaction_mode=IMMEDIATE` + 20 s timeout; no transaction held across a sandbox run | Avoids "database is locked" under concurrent game writes | Plan |
| UI transport | Server-rendered templates + one vanilla-JS `fetch` to a JSON endpoint | No page reload per command on mobile (keyboard stays up); no build step | Plan |
| UI language | English | The challenge texts are English; avoids a mixed-language UI | Plan (assumption) |

## Scope

**In scope:**
- carry-overs (a)–(d)
- SQLite concurrency settings
- `GameSession`/`Attempt` models and game service
- rules/nick, play and done pages
- read-only admin for debugging
- `bench_game` load command and `verification.md`

**Out of scope:**
- 5-minute limit and timer (S-02)
- summary with rank and code (S-03)
- staff lookup (S-04)
- Hall of fame (S-05)
- QR gate (S-06)
- FR-016 soft block
- production server and deploy (F-02)
- hints/solutions, anti-cheat, i18n

## Architecture / Approach

The request flow is browser → `game.views` (thin) → `game.services.submit_command`. The service works in four steps:

1. A short DB read.
2. `reap_stale_once()`, then it takes a semaphore slot.
3. `challenges.sandbox.run_command` runs with no DB transaction open.
4. One short atomic write: it inserts the `Attempt`, increments the counters, and advances `current_slug` only if it is still the slug that was run.

The page renders fully from DB state on load. `play.js` only posts the command and patches the page from the JSON response.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Runner and DB readiness | Carry-overs (a)–(d) fixed + tested; WAL SQLite | Changing `reap_stale`/image check breaks the F-01 harness (guarded by a `verify_challenges` re-run) |
| 2. Game domain | Models, migration, `services.py` with all counting/advance rules | Transaction held across the sandbox run would serialize all players |
| 3. Player UI | Home/play/done pages, JSON command endpoint, JS, admin | Mobile keyboard/UX quirks; XSS via output or description (mitigated: `textContent` + escape-first filter) |
| 4. Measurement | `bench_game` + `verification.md` with 15-player latency and the F-02 concurrency contract | Latency above ~1 s at 15 players (PRD accepts it; would be documented, not fixed here) |

**Prerequisites:** F-01 done (it is). The Docker daemon and `bash-dash-sandbox:latest` built via `sandbox/build.sh` on the dev host.
**Estimated effort:** ~1–1.5 sessions across 4 phases.

## Open Risks & Assumptions

- **UI language assumed English.** The PRD quotes Polish messages (e.g. "zeskanuj kod przy stoisku"). Switching means editing template strings only.
- **The dev-host numbers don't transfer to the event VM.** `bench_game` must be re-run there in F-02, like `verify_challenges`.
- **F-02 must respect the concurrency contract:** total sandbox concurrency = processes × cap, with enough threads per process, and a WAL-safe (`.backup`) DB backup.
- **8 simultaneous abusive commands** (~5 s each) can make other players wait up to the 10 s queue timeout, after which they get "busy". The PRD accepts degraded performance under crowding.
- **These decisions are planner defaults** from an unattended run and still need the user's review.

## Success Criteria (Summary)

- A player can go from nick entry through the first challenges on a phone, seeing output and a verdict for each command. Correct answers advance and every run is counted.
- A reload never loses the game, the counters or the last output. Abusive commands time out in ≤ ~6 s without affecting other players.
- `bench_game --players 15` passes with zero lock errors, internal errors or leaked containers, and the latency is recorded.

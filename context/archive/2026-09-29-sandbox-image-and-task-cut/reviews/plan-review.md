<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Sandbox Image and Task Cut Implementation Plan

- **Plan**: context/changes/sandbox-image-and-task-cut/plan.md
- **Mode**: Deep (claims checked inline against the code, plus small Docker experiments on the dev host)
- **Date**: 2026-09-29
- **Verdict**: REVISE (before triage) → SOUND (after fixes)
- **Findings**: 0 critical, 5 warnings, 4 observations

> This review ran unattended. The user triaged the findings afterwards (via the orchestrator) on 2026-09-29: all 9 were accepted and applied to plan.md, plan-brief.md and PRD FR-004. Verdict after fixes: SOUND.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

Grounding: 9/9 paths ✓ (`config/settings.py`, `pyproject.toml`, `uv.lock`, upstream `Dockerfile-cmd`, `cmd/runcmd/runcmd.go`, `internal/runcmd/runcmd.go`, `internal/challenge/{runner,checks,randomizers}.go`), 8/8 symbols/claims ✓, brief↔plan ✓ (one wording gap noted in F1).

Upstream claims confirmed at commit `09a3d7ad1d6c…`:
- The repo-root `challenges.yaml` is byte-identical to `internal/challenge/challenges.yaml`.
- 42 untagged challenges, none with `dir`/`img`. The first is `hello_world` and the last is `IPv4_listening_ports`.
- `rndTable` has 9 main-set entries and `checkTable` has 11. `print_sorted_by_key` writes `aux` (`challenges.yaml:1225`).
- `create_symlink` uses absolute paths (`challenges.yaml:728`, `checks.go:284-289`).
- Timeouts are `CmdTimeout` 5 s and `RunCmdTimeout` 6 s (`config.go:51,53`). One context is shared by the first run and the randomizer re-run (`runcmd.go:80,113,146`).
- runcmd uses `Setpgid` and a process-group SIGKILL (`runcmd.go:198,213`), and falls back from base64 to raw text (`cmd/runcmd/runcmd.go:42-48`).
- The `CmdResponse` fields match `server.go:34-41`.
- The upstream runner sets memory to 10e+7 with network `none` (`runner.go:92-93`).

The fixtures total 792 KB. The largest challenge directory holds 5 KB. Every file is owner-writable, and there is one relative symlink (in `list_files_adv`, which is not in the main set).

Docker experiments on the dev host (Docker 29.8.1, 8 cores, json-file, cgroup v2):
- A container started under the full profile (read-only, two tmpfs mounts, uid 1000, caps dropped) takes 0.13–0.19 s end to end.
- The `find_primes` example took 0.86 s per run at `--cpus 0.5` and 3.85 s per run at `--cpus 0.125`.
- Under `json-file max-size=1m`, a 600 KB JSON line came back intact and parsable. A 3 MB line came back cut down to its last 1728 characters.

## Key Decisions: assessment (planner defaults — reviewed; user accepted the resolutions below on 2026-09-29)

| Decision | Holds up? | Evidence / alternative |
| --- | --- | --- |
| Read-only rootfs + 16 MB tmpfs `/var/challenges` (entrypoint copies from `/opt/challenges`) | **Yes.** | Fixtures are at most 5 KB per challenge, so 16 MB is roughly 3000× headroom. The tmpfs is charged to the memory cgroup and disappears with the container. The alternative is a writable layer with a cleanup step. overlay2 has no per-container disk quota unless it runs on xfs with pquota, so a `dd` running for 5 s at concurrency N could fill the host disk. Keep this design. One gap: `/dev/shm` (64 MB by default) is still writable (F7). |
| uid 1000 `player` | **Yes.** | All fixtures are owner-writable, `cp -a` keeps player ownership, and even the `rm -rf /var/challenges/delete_files` expected-failure behaves as it does under root. The alternative is root with `cap_drop=ALL`. Without userns remapping, container uid 0 is host uid 0, so non-root is cheap insurance. Keep. |
| 100 MB memory, no swap | **Yes, with one caveat.** | This is the upstream limit (`runner.go:93`). The worst case for the tmpfs mounts is 32 MB of it. The caveat: runcmd buffers all of the command's output in memory (`CombinedOutput`, `runcmd.go:206`), so a `yes` flood gets runcmd itself (PID 1) OOM-killed and the player sees an internal error (F3). |
| 64 pids | **Yes.** | Every example is a sequential pipeline. `GOMAXPROCS=1` keeps the Go runtime threads in single digits. |
| 0.5 CPU | **Yes, per container. Not as a guarantee for the host.** | `find_primes` stays around 1 s per run at 0.5 CPU on the dev box. However, `nano_cpus` limits each container, not the total. Eight CPU spinners on a 2-vCPU event VM would still saturate it. The real guard is S-01's concurrency cap, sized from host cores. The alternative (`cpu_shares` weights only) never slows an idle host, but does not bound a single abuser, so keep 0.5. It does make the latency cut depend on the hardware it is measured on (F1). |
| `GOMAXPROCS=1` | **Yes.** | Harmless. The only side effect is that the variable is visible to player commands. |
| json-file log, `max-size=1m` | **Partly.** | It protects the host disk. But runcmd prints Output inside a single JSON line, so any command printing more than about 1 MB produces a truncated line that cannot be parsed, and the result becomes `error_internal` (confirmed by the experiment above; see F3). Keep the cap and map this case to a clear error for the player. |
| Static runcmd, `CGO_ENABLED=0` | **Yes.** | go-sqlite3 v1.14.17 ships a `!cgo` stub driver (`static_mock.go`), so `_ "github.com/mattn/go-sqlite3"` compiles and errors only when opened, which `-cmd` mode never does. The rest of the imports (docker client, prometheus, gorilla) are pure Go. It was not built during this review (no Go toolchain or builder image locally), but confidence is high, and the `bullseye` fallback is sound. |
| Cut rule (any failure / sequential p95 > 4.0 s / accepted `expected_failures`) | **Partly.** | Cutting on correctness holds. Cutting on accepted expected_failures holds, but the plan contradicts itself on whether that condition blocks the command's exit code (F5). The latency condition is measured on the wrong hardware and load, and "p95" of 3 samples is really the maximum (F1). Too few runs to catch randomizer edge cases (F6). The rule also cannot catch the FR-004 gap: 20/42 challenges accept a plain `echo` of the answer (F2). |
| `challenges/excluded.yaml` (`slug: reason`), upstream YAML untouched | **Yes.** | It keeps the vendored code pristine, the typo guard fails fast at load time, and each cut carries its reason. The alternative is a DB/admin toggle, so staff could cut a challenge that breaks during the event without a deploy. That belongs to S-01/S-04 if at all. Changing the set in the middle of the event makes scores incomparable under "most tasks solved" ranking, so a file plus a deploy is the right friction for now. |

## Findings

### F1 — Latency cut is measured on the wrong hardware and load

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 3 §2 (cut rule, second condition); Performance Considerations
- **Detail**: The cut rule applies p95 > 4.0 s to the *sequential* runs on the 8-core dev host. In the event, what matters is the 5 s budget inside the container, shared by the first run and the randomizer re-run (`runcmd.go:80,146`), under concurrent load on an event VM whose size is unknown (roadmap OQ 9, PRD OQ 7). Measured here: `find_primes` takes 0.86 s per run at 0.5 CPU but 3.85 s per run at 0.125 CPU, so two runs overshoot the 5 s budget. Eight concurrent players on a 2-vCPU VM get about 0.25 CPU each, so a challenge that passes the dev sweep easily could still time out at the event. Also, with `--repeat 3`, "p95" is effectively the slowest of the three runs. The brief's "does not slow a concurrent player" is also stronger than the canary's check that each run finishes in 6 s or less.
- **Fix A ⭐ Recommended**: Gate latency on the parallel stage as well, and emulate the target host.
  - Add `--host-cpus N` to `verify_challenges`. It applies `cpuset_cpus` to all sweep containers, harness only, never to `SANDBOX_RUN_PROFILE`.
  - Apply the 4.0 s rule to the p95 of the parallel stage at the expected concurrency.
  - Record in `verification.md` that the result must be re-run on the VM (F-02 already plans this).
  - Strength: Cuts reflect event conditions. The data already feeds S-01's concurrency cap.
  - Tradeoff: One more flag. The target core count is a guess until F-02 settles the VM.
  - Confidence: MED — the cpuset emulation roughly matches the VM but is not exact.
  - Blind spot: The event VM's actual size and expected player concurrency are still unknown.
- **Fix B**: Take latency out of the cut rule entirely.
  - Cut only on correctness. Report latency as information, and require S-01 to size its concurrency cap so that each container keeps at least 0.5 CPU (concurrency ≤ 2 × cores).
  - Strength: The cut list stops depending on hardware. The problem goes to the component that actually controls load.
  - Tradeoff: A slow challenge could still time out at the event if S-01 sizes its cap badly.
  - Confidence: MED.
  - Blind spot: S-01 has not been planned yet.
- **Decision**: FIXED (Fix A) — harness-only `--host-cpus N` (cpuset pinning); 4.0 s p95 rule applies to sequential and parallel stages; F-02 VM re-run made mandatory.

### F2 — FR-004 "printing the answer is rejected" is false for 20/42 challenges

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Phase 3 §2 (cut rule, third condition); PRD FR-004 and Business Logic
- **Detail**: FR-004 and the PRD's Business Logic say that just printing the expected output does not pass, because of the re-run on randomized data. In the main set, only 9 challenges have a randomizer and 11 have a check. The other 20 (hello_world, current_working_directory, print_file_contents, last_lines, find_string_in_a_file, and 15 more) compare fixed `expected_output` lines, so `printf` of the right text passes. For these, `expected_failures` is at most `echo "nope"`, and 22 main-set challenges have no expected_failures at all. The plan's "known-wrong answer accepted" condition therefore cannot detect this, and F-01 lists FR-004 in its refs without addressing it. Cutting all 20 would gut the game. The PRD Non-Goals (no anti-cheat; "whoever hacks it deserves 42/42") suggest accepting it.
- **Fix**: Add a report-only "printable" column to `verify_challenges`. It probes each challenge with `printf '%s\n'` of the expected lines and marks the ones that accept it, which also documents the gap. Record the count in `verification.md`, and have the user decide whether to amend the FR-004 / Business Logic wording to "for challenges with randomized data" rather than cutting.
  - Strength: Makes the gap explicit without shrinking the game, and fits the PRD Non-Goals.
  - Tradeoff: Weakens a PRD guarantee on paper.
  - Confidence: HIGH — counted directly from `challenges.yaml`, `rndTable` and `checkTable`.
  - Blind spot: Whether the user sees FR-004 as a hard requirement for the prize ranking.
- **Decision**: FIXED (report only) — printable probe column added to the sweep and `verification.md`, never cuts; PRD FR-004 reworded to apply only to challenges with randomized data or a check.

### F3 — Large output and output floods show up as internal errors

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details (container lifecycle); Hardening profile (`log_config`); Phase 3 abuse suite
- **Detail**: runcmd buffers the whole combined output in memory (`runcmd.go:206`) and prints it as a single JSON line on stdout (`cmd/runcmd/runcmd.go:49`). This fails in two ways:
  - An output of roughly 1 MB or more exceeds the json-file `max-size=1m`, the line is truncated from the front (reproduced: a 3 MB line came back as its last 1728 characters), and the last stdout line cannot be parsed, so the result is `error_internal`.
  - A `yes` flood grows runcmd's buffer until the 100 MB cgroup OOM-kills runcmd, which is PID 1. The container exits 137 and prints no JSON, so the result is again `error_internal`.

  The abuse suite asserts only `correct=False`, within 7 s, and the container gone, so it passes while hiding this. For the player, an honest mistake such as `seq 1 1000000` or `cat` on a big file reads as "the system broke", and it still counts as an attempt.
- **Fix**: Tell these cases apart from real internal errors.
  - In `run_command`, read `container.attrs["State"]["OOMKilled"]` (via `reload()` before removing) and return `error="Command used too much memory/output"` instead of `error_internal`.
  - When the log is at least 1 MB and cannot be parsed, return `error="Output too large"`.
  - Add a `seq 1 300000` scenario (about 2 MB) to the abuse suite, and assert on those error kinds.
  - Keep the 1 MB cap.
  - Strength: Players get a truthful message, and internal-error metrics stay meaningful for S-01.
  - Tradeoff: About 10 lines and one extra API call per failed run.
  - Confidence: HIGH — truncation reproduced on this host, and the buffering is visible in the code.
  - Blind spot: The exact byte threshold depends on json-file's per-line overhead; about 900 KB of Output is the safe assumption.
- **Decision**: FIXED — OOMKilled and truncated/oversized output map to distinct player-facing `error`s; `seq 1 300000` abuse case added; 1 MB log cap kept.

### F4 — runcmd's own timeout is reported as an internal error, not a timeout

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §4 (`SandboxResult`); Phase 3 §3 (integration test)
- **Detail**: When runcmd's 5 s context expires, it returns `ErrTimeout`, which becomes `ErrorInternal: "timed out executing command"` with exit 0 (`runcmd.go:96-97,212-214`). The host 6 s timeout almost never fires, because runcmd always returns first. So `sleep 60`, the most common kind of timeout, ends up as `error_internal` with `timed_out=False`. The plan accepts that ("`timed_out` may be False"), but S-01 then cannot tell a player's timeout from a sandbox failure, and the NFR's "result or timeout" becomes invisible.
- **Fix**: In the parser, map `ErrorInternal == "timed out executing command"` to `timed_out=True`, `error_internal=""`. Assert `timed_out=True` in the `sleep 60` integration test and in the abuse suite.
- **Decision**: FIXED — runcmd "timed out executing command" maps to `timed_out=True`; asserted in unit, integration and abuse tests.

### F5 — Contradiction: is an accepted expected_failure gating or report-only?

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 §1(a) vs. §1 Contract (exit code) vs. §2 (cut rule, third condition)
- **Detail**: Stage (a) calls the `expected_failures` result "a report-only column". The cut rule says an accepted expected_failure means the challenge is cut. The exit-code rule mentions only "passed all runs". An implementer could let a broken verifier through with exit 0.
- **Fix**: Make an accepted expected_failure on a non-excluded challenge fail the run (exit 1), and drop "report-only" from stage (a).
- **Decision**: FIXED — an accepted `expected_failures` entry on a non-excluded challenge fails the run (exit 1).

### F6 — Sample size misses randomizer edge cases; any single failure cuts

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 §1(a), §2 (cut rule, first condition)
- **Detail**: Go's `math/rand` is auto-seeded, so every run of the 9 randomized challenges sees different data (`randomizers.go:62-68`). Four runs (3 sequential plus 1 parallel) rarely catch a 1-in-20 edge case, and at the event that edge case would reject a correct player answer about 5% of the time. Meanwhile, "any failure in any run" cuts a challenge because of a one-off infrastructure hiccup (`error_internal`). The manual `--repeat 10` step softens this only if someone remembers to run it.
- **Fix**:
  - Default to 20 runs for challenges with a randomizer.
  - In the cut decision, count only `correct=False` with an `error` (verifier said no) or `timed_out`.
  - Report `error_internal` separately, and have it fail the run without cutting the challenge.
- **Decision**: FIXED — randomized challenges run 20× (`--repeat-randomized`); cut only on verifier "no" or timeout; `error_internal` reported separately, fails the run, never cuts.

### F7 — `/dev/shm` and `/dev/mqueue` stay writable under `--read-only`

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Hardening profile table; Phase 3 abuse suite (disk fill)
- **Detail**: Docker mounts a 64 MB `/dev/shm` tmpfs that `--read-only` does not cover. It is memory-charged, so the 100 MB limit bounds it and it does not threaten the host. But it is not in the profile table or the disk-fill abuse test, which weakens the "single source of truth" claim.
- **Fix**: Add `shm_size="1m"` to `SANDBOX_RUN_PROFILE` and add `/dev/shm` to the disk-fill scenario.
- **Decision**: FIXED — `shm_size="1m"` in the profile; disk-fill abuse covers `/dev/shm`.

### F8 — No cleanup for containers orphaned by a killed caller

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details (container lifecycle); Phase 2 §4
- **Detail**: `remove(...)` in `finally` does not run if the Python process is SIGKILLed or restarted between `run` and `remove`, for example on a deploy or a gunicorn worker timeout. The `bash-dash.sandbox` label makes leaks detectable, but nothing removes them. The containers stop on their own within about 5 s but stay in `docker ps -a`.
- **Fix**: Add `sandbox.reap_stale(max_age_s=60)`, which removes labelled containers that have exited or are older than 60 s. Call it at the start of `verify_challenges`, and note it for S-01 app startup.
- **Decision**: FIXED — `sandbox.reap_stale()` added, called at the start of `verify_challenges`; S-01 startup note.

### F9 — Small contract gaps in Phase 2

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §2, §4
- **Detail**: There are three gaps:
  1. `config/settings.py` imports only `Path` (line 13), but the contract uses `os.environ.get`.
  2. The phrase "`docker.from_env()`, reused module-wide" is ambiguous. If the client is created at import time, `manage.py check` and the Docker-free unit tests break on machines without Docker.
  3. The plan does not say what happens when the daemon is down or the image is missing. `containers.run` tries to pull the missing local tag and raises `docker.errors.ImageNotFound`/`APIError`, and the plan does not say whether that raises or becomes `error_internal`.
- **Fix**: Add `import os`. Specify a lazily created, cached client. State that `docker.errors.DockerException` raised before the container exists propagates as a `SandboxUnavailable` exception, and that anything after the container starts becomes `error_internal`.
- **Decision**: FIXED — `import os` in settings; lazy module-cached Docker client; `SandboxUnavailable` before the container exists, results (`error_internal` etc.) after.

## Triage Summary

- Fixed: F1 (Fix A), F2 (report only), F3, F4, F5, F6, F7, F8, F9 (9)
- Skipped / Accepted / Dismissed: none
- Key Decisions defaults: reviewed; the read-only rootfs + tmpfs, uid 1000, limits, static runcmd and `excluded.yaml` stand; the limits gained `shm_size` 1 MB, and the cut rule was revised per F1, F5, F6 and F2.
- Verdict after fixes: REVISE → SOUND

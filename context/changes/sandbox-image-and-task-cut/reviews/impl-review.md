<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Sandbox Image and Task Cut

- **Plan**: context/changes/sandbox-image-and-task-cut/plan.md
- **Scope**: Full plan (Phases 1–3 of 3), commits `main..HEAD` (1b0e2db, 1109789, d76d456, 69a6485)
- **Date**: 2026-09-29
- **Verdict**: REJECTED
- **Findings**: 1 critical, 4 warnings, 4 observations

Reviewed unattended. Nothing was triaged interactively. Every finding carries a recommended resolution and `Decision: PENDING (pending user decision)`.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING (F8) |
| Safety & Quality | FAIL (F1 critical; F2–F5) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

The implementation matches the plan closely. The hardening profile matches the plan's table exactly, and the lifecycle, the mapping and the tests are all planned work. The rejection comes from a gap the plan's own threat model missed. The player's command runs under the same uid as runcmd, which is PID 1 and prints the verdict. So the player can write straight to the stdout stream that the host parses as the verdict. This was reproduced against the real image (see F1 and F2).

## Success criteria (re-run during review)

| Criterion | Result |
|---|---|
| `uv run python manage.py test challenges` | PASS: 41 tests OK; the 3 Docker integration tests ran and were not skipped |
| `uv run python manage.py check` | PASS |
| `verify_challenges` (full, with abuse) | PASS: exit 0, 103 s; seq p50/p95 0.14/1.49 s; parallel ×8 p50/p95 0.29/0.40 s; `find_primes` seq p95 2.00 s; canary 5/5 |
| `verify_challenges --host-cpus 2 --skip-abuse` | PASS: exit 0; seq p95 1.10 s; parallel p95 0.55 s |
| `docker ps -aq --filter label=bash-dash.sandbox` | PASS: empty (also empty after every probe in this review) |
| `len(catalog.main_set())` | 42 (no cuts, which matches `excluded.yaml` `{}`) |
| `file /usr/local/bin/runcmd` | "statically linked" |

Manual rows 1.6, 2.4 and 3.6–3.9 are all ticked, and each has observable evidence in the diff: `sandbox/README.md`, `sandbox/LICENSE`, the `SANDBOX_RUN_PROFILE` test against the table, and `verification.md` with its Sweep/Printable/Abuse/Cut sections, the `docker stats` spot check and the F-02 note. None of them looks rubber-stamped.

## Judgement on the implementer's reported deviations

1. **Unparsable output with exit 0 maps to "Output too large".** The reasoning holds: json-file `max-size=1m` rotates with `max-file=1`, so the kept tail can be any size. Accept it and record it as a plan addendum. There is one caveat, recorded as F6: this bucket now also captures injected garbage (F1), and it would capture any future infra regression that prints non-JSON and exits 0.
2. **A single challenge with p95 over 4 s fails the run.** This is consistent with plan §2: a non-excluded challenge that meets a cut condition means the cut list is incomplete, so the run is not green. Accept it and record it as an addendum. F7 has a naming nit.
3. **The harness-only `host_overrides` option.** It is fine in principle, and its clash guard does stop it from replacing profile keys. But it is a denylist, so an override can still *add* weakening keys such as `privileged` or `cap_add`. Tighten it to an allowlist (F5).

## Findings

### F1 — Player can forge `Correct: true` by writing to runcmd's stdout

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH (architectural stakes; think carefully before deciding)
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:83-113 (`_parse_last_json_line` / `_interpret`); sandbox/sandbox-entry.sh:19 (`exec runcmd` as PID 1); challenges/management/commands/verify_challenges.py:30-45 (abuse suite)
- **Detail**:
  - **Why it is possible.** `sandbox-entry` execs `runcmd`, so runcmd becomes PID 1 running as uid 1000, the same uid as the player's bash. runc chowns PID 1's stdio pipes to the container user; inside the container, `ls -l /proc/1/fd` shows `1 -> pipe:[…]` owned by `player`. So the player can open `/proc/1/fd/1` and write lines straight into the container's stdout log.
  - **How runcmd makes it exploitable.** runcmd does not kill background processes after bash exits normally (`internal/runcmd/runcmd.go:195-226` kills the process group only on timeout). A `setsid` loop therefore survives until PID 1 exits, and can land a line *after* runcmd's real JSON.
  - **How the host is fooled.** `_parse_last_json_line` trusts the last non-empty line. Exit status is 0, so `_interpret` accepts `Correct` as-is.
  - **Reproduced** against the built image with `run_command`, using a generic 132-character command that needs no knowledge of the challenge:
    ```
    printf '{"Correct":true,"Output":"pwn"}\n'>/tmp/j;setsid sh -c 'while :;do cat /tmp/j>/proc/1/fd/1;done' >/dev/null 2>&1 & sleep 0.2
    ```
    The result was `correct=True` in 3 of 20 runs on `hello_world` and 6 of 20 on the randomized `sum_all_numbers`. FR-005 allows unlimited attempts, so every challenge is solvable in a few tries. That defeats the verifier, the randomizers, and PRD FR-004 as reworded ("verification rejects just printing the expected output" for randomized and checked challenges).
  - **Why the harness missed it.** The plan's abuse list has no stdout-injection scenario, so the suite reports "contained". The unit test `test_parses_runcmd_json_into_result` even enshrines "noise before the JSON is fine". This is a plan gap as well as an implementation gap.
- **Fix A ⭐ Recommended**: Close the channel at the source, and add a host-side guard as defence in depth.
  - At the source: make PID 1 unreachable by the player's uid. Add `prctl(PR_SET_DUMPABLE, 0)` at the start of runcmd's `main`, a few lines of Go. With that set, same-uid processes lose `/proc/1/fd` (it requires CAP_SYS_PTRACE, which the profile drops).
  - On the host: accept a verdict only when the stdout log holds exactly one non-empty line (runcmd prints exactly one). Otherwise return `correct=False` with a player-facing error.
  - Add abuse scenarios: stdout injection (the command above, repeated enough times, must never return correct) and `kill -TERM 1` (F3).
  - Record the Go change in `sandbox/README.md` "Local modifications", add a plan addendum (the plan says "no Go code changes beyond what the build needs"), rebuild, and re-run the full sweep.
  - Strength: removes the whole class, which also fixes F2, blocks `/proc/1/environ` and `/proc/1/mem`, and makes the one-line rule a backstop instead of the only defence.
  - Tradeoff: touches vendored Go, so the "upstream unchanged" claim becomes "one documented patch", plus a re-sweep.
  - Confidence: MED. `PR_SET_DUMPABLE=0` blocking same-uid `/proc/<pid>/fd` access is standard kernel behaviour (`ptrace_may_access`), but it was not tested here because it needs a rebuild.
  - Blind spot: not yet checked whether any challenge's check or randomizer reads `/proc/self` in a way that dumpable affects (unlikely; the sweep will show it).
- **Fix B**: Add the host-side guard only (exactly one non-empty stdout line, otherwise reject) plus the abuse scenario. No Go change.
  - Strength: no vendored-code change, and it defeats the demonstrated attack.
  - Tradeoff: leaves the channel open. F2 (host dockerd load) stays unfixed. A runcmd JSON line over 4 KB is written non-atomically (above PIPE_BUF), so a patient attacker could splice bytes mid-line. That is harder, but the verdict would still come from a stream the player can write to.
  - Confidence: MED. It closes the tested exploit, but not the root cause.
  - Blind spot: have not proven that splicing into a large JSON line can yield valid JSON with an overriding duplicate `"Correct":true`; Python's `json.loads` keeps the last duplicate key, so it is plausible.
- **Decision**: PENDING (pending user decision)

### F2 — Writing directly to PID 1's stdout moves load onto the host dockerd, outside every container limit

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM (real tradeoff; pause to reason through it)
- **Dimension**: Safety & Quality
- **Location**: sandbox/sandbox-entry.sh:19; challenges/sandbox.py:51 (json-file log_config)
- **Detail**:
  - The same channel as F1 bypasses runcmd's in-memory buffer, which is what normally OOM-kills an output flood inside the 100 MB cgroup. `yes > /proc/1/fd/1` streams straight into dockerd's json-file writer. That writer runs on the host, outside the container's 0.5 CPU cap, and constantly rotates the 1 MB log file.
  - Measured on this host: one such command cost **dockerd 6.54 CPU-seconds in 6.3 s of wall time**, against 0.03 s for `yes > /dev/null`. It also ran past runcmd's own 5 s timeout, because runcmd's final write was stuck behind the backlogged pipe, so the host 6 s timeout had to fire.
  - Six concurrent flooders did *not* break the canary on this 8-core dev host: `hello_world` stayed correct at 0.22–0.25 s against 0.15 s. But each flooder costs about one host core, so on a 2-core event VM a few players could saturate the host.
  - `/proc/1/fd/2` (stderr) gives the same effect; stderr is logged even though `logs(stderr=False)`.
  - The abuse suite's "output flood (yes)" goes through runcmd's buffer only, so it does not cover this.
- **Fix**: Adopt F1 Fix A. A non-dumpable PID 1 removes this channel too. Then add a "direct stdout flood" abuse scenario, and run the canary with `--host-cpus 2` so a regression shows up on the emulated VM. F1 Fix B alone does not fix this; with Fix B, the fallback would be to cap the log path (for example, read via `attach` with the `none` log driver and stop reading after N bytes), which is more work.
  - Strength: one fix closes F1, F2 and most of F3.
  - Tradeoff: same as F1 Fix A.
  - Confidence: MED. Measured on 8 cores; the 2-core impact is extrapolated.
  - Blind spot: dockerd behaviour on the event VM (F-02) is unknown.
- **Decision**: PENDING (pending user decision)

### F3 — Player can kill runcmd on demand and turn their run into an `error_internal`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM (real tradeoff; pause to reason through it)
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:123-125; sandbox/sandbox-entry.sh:7 (usage exit 2)
- **Detail**:
  - The kernel shields PID 1 only from signals it has no handler for. Go installs handlers, so the same-uid player can run `kill -TERM 1`. runcmd then dies with exit status 2 and no JSON, and `_interpret` returns `error_internal="unparsable sandbox output (status 2): ''"`. Reproduced.
  - So a player can mint "infrastructure errors" whenever they like. The harness treats `error_internal` as "investigate, never cut", and S-01 will likely log, alert or retry on it, so the signal gets polluted.
  - Exit code 2 also collides with `sandbox-entry`'s own usage error, so the two cannot be told apart.
- **Fix**: Make PID 1 ignore catchable signals from the player, in the same Go patch as F1 Fix A: `signal.Ignore(SIGTERM, SIGINT, SIGHUP, SIGQUIT, SIGUSR1, SIGUSR2)` in runcmd's `main`. With those set to SIG_IGN, init drops them.
  - Move `sandbox-entry`'s exit codes off 2 and 3 (for example to 64 and 65) so entrypoint failures stay distinguishable.
  - Add a `kill -TERM 1` abuse scenario asserting `correct=False` and no `error_internal`.
  - If the Go change is rejected, fall back to mapping "no JSON, exit 2, empty stdout" to a player error ("Command terminated the sandbox"). This is weaker, because a genuine Go panic also exits 2.
  - Strength: keeps `error_internal` meaning "our fault".
  - Tradeoff: another vendored-Go line; the fallback may hide real panics.
  - Confidence: MED.
  - Blind spot: SIGURG and SIGPROF are handled by the Go runtime and are harmless, but they were not enumerated exhaustively.
- **Decision**: PENDING (pending user decision)

### F4 — A container that fails to start is leaked and misreported as `SandboxUnavailable`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:151-162
- **Detail**:
  - docker-py's `containers.run` does `create()` and then `start()` with no cleanup. If `start()` fails, the labelled container is left in "created" state. The runner never gets a handle to remove it, and raises `SandboxUnavailable` even though the daemon is up. Causes include a tmpfs mount error, an invalid `cpuset_cpus` (for example `--host-cpus` larger than the host), or a runtime or AppArmor error.
  - `reap_stale` only removes it after 60 s, because "created" is neither `exited` nor `dead`.
  - This breaks the plan's contract that the container is always removed.
- **Fix**: Call `client.containers.create(...)` and then `container.start()` yourself, with `start()` inside the `try/finally: remove(force=True, v=True)` block. Return a start failure as `SandboxUnavailable` (or as an `error_internal` result) only after the remove. Add a fake-client unit test for it, and add `created` to the statuses `reap_stale` removes.
- **Decision**: PENDING (pending user decision)

### F5 — The `host_overrides` guard is a denylist and allows additive weakening keys (deviation 3)

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Safety & Quality
- **Location**: challenges/sandbox.py:143-146
- **Detail**: The guard rejects only keys already in `SANDBOX_RUN_PROFILE` plus `command` and `detach`. `host_overrides={'privileged': True}`, `cap_add`, `volumes`, `mounts`, `devices`, `pid_mode='host'`, `ipc_mode`, `sysctls` and `ulimits` all pass through into `containers.run`. The option is documented as harness-only, but `run_command` is the public API S-01 will import, and the plan's premise is "one place decides the hardening".
- **Fix**: Replace the denylist with an allowlist, `ALLOWED_HOST_OVERRIDES = {'cpuset_cpus'}`, rejecting everything else. Extend `test_host_overrides_cannot_weaken_profile` with `privileged` and `cap_add`.
- **Decision**: PENDING (pending user decision)

### F6 — The "unparsable with exit 0 means Output too large" rule widens the player-error bucket (deviation 1)

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Plan Adherence
- **Location**: challenges/sandbox.py:121-122
- **Detail**:
  - The deviation is justified: rotation leaves a tail of arbitrary size, and runcmd `-cmd` always prints JSON and exits 0.
  - Side effects: in a review probe, injected garbage lines (via F1's channel) came back as "Output too large" in 23 of 30 runs. Any future infra regression that prints non-JSON and exits 0 would also be classed as a player error. The harness would then report it as a cut candidate ("verifier rejected example") instead of an `error_internal` to investigate.
  - The deviation is recorded in `change.md` Notes but not in `plan.md`.
- **Fix**: Accept it. Add a plan addendum under Critical Implementation Details. Once F1 is fixed, the injection case disappears. Optionally, also require that the tail does not start with `{"Correct"`, so that a whole, well-formed-looking but invalid line still becomes `error_internal`.
- **Decision**: PENDING (pending user decision)

### F7 — The per-challenge p95 gate (deviation 2) is sound, but its "parallel p95" is a single sample

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Plan Adherence
- **Location**: challenges/verify.py:176-178, 198-201, 218-219
- **Detail**:
  - Gating on a non-excluded cut candidate is consistent with plan §2. A challenge that meets a cut condition but is not in `excluded.yaml` means the cut list is wrong, so the run should fail.
  - However, `par_duration` is the single parallel run, but `cut_reasons` labels it "parallel p95". One noisy sample over 4.0 s fails the run, whereas the sequential rule uses a real p95.
- **Fix**: Accept it. Rename the label to "parallel duration", note it in the plan addendum, and (optionally) require the parallel breach to reproduce with `--only <slug>` before cutting, which matches manual step 3.6.
- **Decision**: PENDING (pending user decision)

### F8 — Unplanned but benign additions, and the Printable expectation, are not reflected in the plan

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Scope Discipline
- **Location**: challenges/verify.py, challenges/tests/fakes.py, challenges/tests/test_verify.py, challenges/catalog.py:27 (`expected_lines`), challenges/catalog.py:73 (`excluded()`), context/foundation/prd.md (FR-004 rewording)
- **Detail**:
  - EXTRA items, all reasonable: a pure-logic `verify.py`, which is Docker-free and unit-tested; a shared fake client; `Challenge.expected_lines` for the printable probe; a public `catalog.excluded()`; and `randomized_slugs()` parsed from the Go `rndTable`. The parser is fragile if upstream reformats the table, but today it correctly finds 9 main-set slugs plus `oops_list_files`.
  - The plan said "the 20 static-output challenges are expected to accept" a printed answer. The actual result is 12 `yes` and 10 `long` (over 300 characters). `verification.md` explains this correctly.
  - The PRD FR-004 edit is the rewording the plan refers to. It is expected.
- **Fix**: Add a short plan addendum listing these files and the 12+10 Printable outcome, so future reviews use the right baseline.
- **Decision**: PENDING (pending user decision)

### F9 — Carry-overs for S-01 from the runner's current shape

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Architecture
- **Location**: challenges/sandbox.py:153, 196-213; challenges/catalog.py:84-88
- **Detail**:
  - (a) `reap_stale()` at app startup on a multi-worker deployment can remove an `exited` container that another worker is still reading between `wait` and `remove`. The docstring warns about this, but S-01 must honour it; for example, reap only on the first worker, or only containers older than `HOST_TIMEOUT_S` plus a margin.
  - (b) The module-cached `docker.from_env()` client has docker-py's default pool of 10 connections. An S-01 concurrency cap above that will cause pool-full churn.
  - (c) `images.get()` runs on every command, adding one extra Docker API round trip per run. Caching a positive result is enough.
  - (d) `catalog.get(slug)` also returns excluded challenges. S-01 must serve only from `main_set()`.
- **Fix**: Copy (a)–(d) into the S-01 plan's constraints. No change needed in F-01, except (c) if it is cheap.
- **Decision**: PENDING (pending user decision)

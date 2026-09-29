# Sandbox Image and Task Cut Implementation Plan

## Overview

Vendor the cmdchallenge Go sandbox into `sandbox/` and build a hardened `bash-dash-sandbox` Docker image from it. Add a small Python layer (challenge catalog plus container runner) that S-01 will call as-is. Then use a management command to run every main-set challenge's reference solution, plus a set of abuse commands, under the exact production hardening profile. Challenges that fail go on an explicit cut list. This is roadmap item F-01. It resolves PRD Open Question 4 ("Which of the 42 challenges do we cut?") and proves the guardrail that one player's command cannot hurt the game or the host.

## Current State Analysis

- `bash-dash` is a bare Django 6.1 scaffold: `config/` only, `INSTALLED_APPS` is the stock list (`config/settings.py:33`), and the only dependency is `django>=6.1.1` (`pyproject.toml`). There are no apps, tests, Makefile or CI yet. The only verified tooling is `uv run python manage.py check`.
- The upstream source is a local clone at `~/src/cmdchallenge`, commit `09a3d7ad` (MIT, `LICENSE` at the repo root). The Go module is `~/src/cmdchallenge/cmdchallenge/`: `cmd/runcmd`, `internal/{challenge,config,metrics,runcmd,store}`, `var/challenges/` (796 KB), `go.mod`, `go.sum` and `Dockerfile-cmd`.
- `challenges.yaml` (identical at the repo root and in `internal/challenge/`) is embedded into the `runcmd` binary. The 42 main-set challenges are the entries without `tags`. None of them sets `dir` or `img`, so the working dir is always `/var/challenges/<slug>`.
- Upstream invocation (`internal/challenge/runner.go:85-167`) is roughly `docker run --network none --memory 100m -w /var/challenges/<dir> cmd:<arch> runcmd -cmd -slug <slug> <base64 cmd>`. stdout is a single JSON line, `{"Correct","Output","Error","ErrorInternal","ExitCode","Cached"}` (`internal/challenge/server.go:34`), and a non-zero container exit means an internal error. The timeout is 5 s inside the container (`config.go:51`, shared by the first run and the randomizer re-run) and 6 s on the host (`config.go:53`). Successful containers are never removed upstream.
- Inside the container, `runcmd -cmd` runs `bash -O globstar -c` with `Setpgid` and on timeout kills the process group, which needs no capabilities (`internal/runcmd/runcmd.go:195-226`).
  - Randomizers (`randomizers.go:23-41`) and checks (`checks.go:33-54`) `chdir` to the hardcoded `/var/challenges/<dir>` and read or write files there.
- Test harness: upstream `TestChallengesExpectPass` (`internal/challenge/runner_integration_test.go:25-50`) does not compile, because of logr-to-slog API drift. There is no Go toolchain on the host. So there is no reusable harness.
- Host: Docker 29.8.1, amd64, runc, cgroup v2, default seccomp and AppArmor. The target VM architecture is still open (roadmap OQ 9). The image builds for the host arch by default, and arm64 is a build arg away.

## Desired End State

- `sandbox/` holds the vendored Go module with MIT attribution, and a single command, `sandbox/build.sh`, produces the `bash-dash-sandbox:latest` image.
- A Django app `challenges` exposes:
  - `catalog.main_set()`, the ordered list of playable challenges: untagged, minus `challenges/excluded.yaml`;
  - `sandbox.run_command(challenge, command)`, which runs one command under the hardening profile and returns a typed result. The container is always removed.
- `uv run python manage.py verify_challenges` runs every main-set example 3× sequentially (20× for the 9 randomized challenges) and once more under concurrency 8, optionally pinned to N host cores with `--host-cpus N` to emulate the event VM. It then runs the abuse suite. It prints a table with latencies and exits 0 only if every non-excluded challenge passes and every abuse scenario is contained.
- `challenges/excluded.yaml` lists each cut challenge with a one-line reason.
- `context/changes/sandbox-image-and-task-cut/verification.md` records the run: pass/cut table (including the report-only "printable" column), p50/p95 latency sequentially and at concurrency 8, the `--host-cpus` value used, and abuse results. It notes that the sweep must be re-run on the event VM in F-02.
- Verify by running `uv run python manage.py verify_challenges` (exit 0), `uv run python manage.py test challenges`, and checking `docker ps -a --filter label=bash-dash.sandbox` (empty afterwards).

### Key Discoveries:

- 21 of the 42 challenges write into their fixture dir: 11 via checks (`checks.go:33-47`), 9 via randomizers (`randomizers.go:23-34`), plus `print_sorted_by_key` (`challenges.yaml:1225`). So a plain `--read-only` rootfs or a non-root user without chowned fixtures breaks them.
- `create_symlink`'s example and check use absolute `/var/challenges/...` paths (`challenges.yaml:728`, `checks.go:284-289`), so the fixture must live at exactly `/var/challenges/<dir>`.
- `IPv4_listening_ports` greps a static `netstat.out` fixture, so `--network none` is harmless.
- `find_primes` is the heaviest: about 100+ sequential `factor`/`cut` forks, run twice. Expect it to be the slowest under `--cpus 0.5`.
- `pids_limit` counts threads, and Go sizes `GOMAXPROCS` to host CPUs, so set `GOMAXPROCS=1` in the container env.
- `runcmd` links cgo `go-sqlite3` (for its unused server mode). A binary built on the `golang:1.24` Debian image can need a newer glibc than Ubuntu 22.04 ships, while `-cmd` mode never touches sqlite.
- `runcmd` accepts either base64 or raw text (`cmd/runcmd/runcmd.go:42-48`). Always send base64.

## What We're NOT Doing

- No game models, views, sessions, rate limiting or concurrency semaphore. Those belong to S-01 and S-02. The runner is a plain function S-01 will wrap.
- No fixing of broken challenges. They are cut, per PRD Non-Goals. No `12days`/`oops` sets, no `Dockerfile-cmd-no-bin`, no `oops` binary.
- No porting of checks or randomizers to Python, and no Go code changes beyond what the build needs. The Go tests are not repaired.
- No multi-arch image publishing or registry push. It is a local build for the host arch, with `BUILD_ARCH` as an override for F-02.
- No gVisor or user-namespace remapping. These are the daemon-level hardening options, deferred to F-02 if at all.
- No CI workflow. Nothing in this change runs in GitHub Actions, because the sweep needs Docker.

## Implementation Approach

Keep the verified upstream contract (runcmd JSON on stdout, 5 s inner and 6 s outer timeout) and change only how the container is launched. Every playability decision comes from one place, the `SANDBOX_RUN_PROFILE` in `challenges/sandbox.py`. The harness and S-01 therefore run commands under identical hardening, and a challenge that passes the harness passes in the game.

Hardening profile (target):

| Setting | Value | Why |
| --- | --- | --- |
| network | `none` | no egress |
| memory / memswap | `100m` / `100m` | upstream limit, no swap |
| pids_limit | `64` | fork bomb |
| nano_cpus | `0.5` CPU | CPU burn |
| cap_drop | `ALL` | no challenge needs caps |
| security_opt | `no-new-privileges` | |
| user | `1000:1000` (`player`) | defense in depth; fixtures chowned in image |
| read_only rootfs | `true` | protects host disk from the writable layer |
| tmpfs `/var/challenges` | `size=16m,mode=1777,exec` | writable fixture copy, memory-charged, auto-gone |
| tmpfs `/tmp` | `size=16m,mode=1777` | scratch |
| shm_size | `1m` | `/dev/shm` stays writable under `read_only`; shrink it from the 64 MB default |
| env | `GOMAXPROCS=1` | keep threads under pids limit |
| log_config | json-file, `max-size=1m` | cap host disk use from flood output |
| labels | `bash-dash.sandbox=1` | leak detection / cleanup |
| host timeout | 6 s wait, then `kill` + `remove(force=True, v=True)` | NFR ≤ ~6 s |

## Critical Implementation Details

**Fixture copy into tmpfs.** A tmpfs mounted over `/var/challenges` hides the image's fixtures, so the image stores them at `/opt/challenges`. A tiny entrypoint script copies only `/opt/challenges/<dir>` into the tmpfs, `cd`s into it and `exec`s `runcmd -cmd -slug <slug> <b64>`. Do not rely on Docker `working_dir` for `/var/challenges/<dir>`, because the directory does not exist until the copy runs. Docker's `--tmpfs` defaults to `noexec`, so pass `exec` explicitly to keep upstream behaviour for commands that run files from the cwd.

**Static runcmd.** Build `runcmd` with `CGO_ENABLED=0`. This gives a static binary with no glibc coupling. go-sqlite3 falls back to a stub that only errors if the server-mode store is opened, which `-cmd` never does. If the build refuses (a hard cgo import), the fallback is pinning the builder to `golang:1.24-bullseye`, which has an older glibc than Ubuntu 22.04.

**Container lifecycle.** Use `containers.run(detach=True)`, then `wait(timeout=6)`, then `logs(stdout=True, stderr=False)`, then `remove(force=True, v=True)` in a `finally`. Do not use `auto_remove`, because it races with reading logs. A `wait` timeout surfaces as a `requests` read-timeout or connection error. Catch it, `kill` the container, and return `timed_out=True`. Parse only the last non-empty stdout line as JSON. Before removing the container, `reload()` it and read `State.OOMKilled` and the exit code. Map the outcomes like this, never raising to the caller once the container exists:

- JSON with `ErrorInternal == "timed out executing command"`: runcmd's own 5 s timeout (`runcmd.go:212-214`). Set `timed_out=True`, `correct=False` and `error_internal=""`. This, not the host 6 s wait, is the normal timeout path.
- `OOMKilled` true, or exit code 137 with no parsable JSON: set `error="Command used too much memory or output"` and `correct=False`. runcmd buffers all output in memory (`runcmd.go:206`), so an output flood OOM-kills it, and that is a player error, not ours.
- No parsable JSON and the stdout log is 900 KB or more: the 1 MB json-file cap truncated runcmd's single JSON line. Set `error="Output too large (limit about 1 MB)"` and `correct=False`.
- Any other unparsable line or non-zero exit: set `error_internal`.

The Docker client is created lazily on first use and cached in the module, so importing `challenges.sandbox`, `manage.py check` and the unit tests need no Docker. A `docker.errors.DockerException` raised before the container exists (daemon down, image missing; `containers.run` would otherwise try to pull the local tag, so check that the image exists first) is raised as `SandboxUnavailable`. Anything after the container has started becomes a result.

**Orphan cleanup.** The `finally` cannot run if the Python process is killed between `run` and `remove`. `sandbox.reap_stale(max_age_s=60)` force-removes containers labelled `bash-dash.sandbox` that have exited or are older than 60 s. `verify_challenges` calls it before the sweep. S-01 should call it at app startup.

## Phase 1: Vendor the sandbox and build the image

### Overview

Copy the Go module into `sandbox/`, trim the Dockerfile to what we need (runcmd only, static, non-root, fixtures at `/opt/challenges`, entrypoint), and prove one hardened `docker run` by hand.

### Changes Required:

#### 1. Vendored module

**File**: `sandbox/` (new): `cmd/runcmd/`, `internal/` (all packages; runcmd imports store/metrics for server mode), `var/`, `go.mod`, `go.sum`, `LICENSE` (copied verbatim from upstream repo root)

**Intent**: Bring in the verification logic unchanged so correctness stays upstream's. Leave out `cmd/oops`, `cmd/submissions`, `cmd/test`, `Dockerfile-cmd-no-bin` and `test.txt`.

**Contract**: The Go module path is unchanged. `sandbox/internal/challenge/challenges.yaml` is the single source of truth for challenges, and the Python catalog reads the same file.

#### 2. Provenance note

**File**: `sandbox/README.md`

**Intent**: State the upstream URL (gitlab.com/jarv/cmdchallenge), commit `09a3d7ad1d6ca78bc3ad90c5bf7dda85b1087a42`, the MIT copyright line, what was dropped, and the list of local modifications (Dockerfile only).

**Contract**: Satisfies the MIT attribution requirement from `idea.md` §2.

#### 3. Dockerfile

**File**: `sandbox/Dockerfile` (derived from upstream `Dockerfile-cmd`)

**Intent**: Build a multi-stage image with a static `runcmd`, the same apt packages (`jq bc rename bsdmainutils man file`), a `player` user (uid/gid 1000), fixtures copied to `/opt/challenges` owned by `player`, and the entrypoint script. Drop the `oops` build and the `1-experimental` syntax pin (use `docker/dockerfile:1`).

**Contract**: `ARG BUILD_PLATFORM` defaults to `linux/amd64`. `go build` runs with `CGO_ENABLED=0 -ldflags "-w"` for `./cmd/runcmd`. `/usr/local/bin/runcmd` and `/usr/local/bin/sandbox-entry` are present. `USER player`. `ENTRYPOINT ["/usr/local/bin/sandbox-entry"]`.

#### 4. Entrypoint

**File**: `sandbox/sandbox-entry.sh` (copied into the image as `/usr/local/bin/sandbox-entry`)

**Intent**: Copy one fixture dir into the tmpfs, `cd` there, and `exec runcmd`. It must be POSIX `sh`, have no bashrc side effects, and fail loudly (non-zero exit) if the dir is missing.

**Contract**: Args are `<dir> <slug> <base64-cmd>`. It effectively runs `cp -a /opt/challenges/<dir> /var/challenges/ && cd /var/challenges/<dir> && exec runcmd -cmd -slug <slug> <base64-cmd>`.

#### 5. Build script

**File**: `sandbox/build.sh`

**Intent**: Run a one-liner build: `docker build` with `--build-arg BUILD_PLATFORM=linux/${BUILD_ARCH:-<host arch>}` and `-t ${SANDBOX_IMAGE:-bash-dash-sandbox:latest}`, context `sandbox/`.

**Contract**: The script is executable and works from any cwd.

### Success Criteria:

#### Automated Verification:

- Image builds: `sandbox/build.sh` exits 0
- Static binary: `docker run --rm --entrypoint sh bash-dash-sandbox -c 'file /usr/local/bin/runcmd'` reports "statically linked"
- Hardened hello_world passes: `docker run --rm --network none --memory 100m --memory-swap 100m --pids-limit 64 --cpus 0.5 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /var/challenges:size=16m,mode=1777,exec --tmpfs /tmp:size=16m,mode=1777 -e GOMAXPROCS=1 bash-dash-sandbox hello_world hello_world "$(printf 'echo hello world' | base64)"` prints JSON with `"Correct":true`
- A file-writing challenge passes the same way: `create_file` with `touch testfile` prints `"Correct":true`
- Django still boots: `uv run python manage.py check`

#### Manual Verification:

- `sandbox/README.md` and `sandbox/LICENSE` carry the upstream copyright and commit

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Challenge catalog and sandbox runner

### Overview

Add the `challenges` Django app with the two modules S-01 will import, plus unit tests that need no Docker.

### Changes Required:

#### 1. Dependencies

**File**: `pyproject.toml` / `uv.lock`

**Intent**: Add `docker` (the Docker SDK for Python) and `pyyaml` with `uv add`.

**Contract**: Both are runtime dependencies. The lockfile is updated.

#### 2. App and settings

**File**: `challenges/` (new app: `__init__.py`, `apps.py`, `tests/`), `config/settings.py`

**Intent**: Register the app and add sandbox settings with env overrides so F-02 can retarget the image.

**Contract**:
- `import os` at the top of `config/settings.py` (it currently imports only `Path`)
- `INSTALLED_APPS += ["challenges"]`
- `SANDBOX_IMAGE = os.environ.get("BASHDASH_SANDBOX_IMAGE", "bash-dash-sandbox:latest")`
- `CHALLENGES_YAML = BASE_DIR / "sandbox/internal/challenge/challenges.yaml"`
- `CHALLENGES_EXCLUDED = BASE_DIR / "challenges/excluded.yaml"`

#### 3. Catalog

**File**: `challenges/catalog.py`, `challenges/excluded.yaml`

**Intent**: Load the YAML once, keep untagged entries in file order, drop the slugs listed in `excluded.yaml`, and expose an immutable `Challenge` record.

**Contract**:
- `Challenge(slug, title, description, dir, example, expected_failures)`. `title` comes from `disp_title`, falling back to the slug. `dir` defaults to the slug.
- `all_main_set() -> list[Challenge]` returns 42 challenges and ignores exclusions.
- `main_set() -> list[Challenge]` returns the playable challenges.
- `get(slug) -> Challenge`.
- `excluded.yaml` is a mapping `slug: reason` and starts empty (`{}`). An unknown slug in `excluded.yaml` raises at load time, to catch typos.

#### 4. Runner

**File**: `challenges/sandbox.py`

**Intent**: Run one command under the hardening profile, with the lifecycle from Critical Implementation Details. Module-level `SANDBOX_RUN_PROFILE` is the single definition of hardening.

**Contract**:
- `run_command(challenge: Challenge, command: str, *, client=None) -> SandboxResult`.
- `SandboxResult(correct: bool, output: str, error: str, error_internal: str, exit_code: int | None, timed_out: bool, duration_s: float)`.
- Raises `ValueError` for commands over 300 characters, the upstream limit.
- Raises `SandboxUnavailable` (defined in `challenges/sandbox.py`) when Docker fails before the container exists. Once the container has started, every outcome is a `SandboxResult`, using the mapping in Critical Implementation Details: runcmd timeout → `timed_out=True`; OOM kill → memory/output `error`; truncated log over 900 KB → "output too large" `error`; anything else → `error_internal`.
- Output is truncated to 64 KB.
- The container is always removed, even on exceptions.
- The client defaults to a lazily created, module-cached `docker.from_env()`.
- `reap_stale(max_age_s=60, *, client=None) -> int` removes stale labelled containers and returns how many it removed.

#### 5. Unit tests

**File**: `challenges/tests/test_catalog.py`, `challenges/tests/test_sandbox.py`

**Intent**:
- **Catalog:** 42 untagged challenges in order, the first `hello_world` and the last `IPv4_listening_ports`; exclusions applied; an unknown excluded slug raises.
- **Runner:** tested with a fake Docker client. It covers:
  - JSON parsing;
  - runcmd's "timed out executing command" mapping to `timed_out=True` with an empty `error_internal`;
  - `OOMKilled` mapping to the memory/output `error`;
  - an unparsable log of 900 KB or more mapping to the "output too large" `error`;
  - any other non-zero exit mapping to `error_internal`;
  - a host wait timeout mapping to `timed_out` plus kill;
  - a missing image or daemon error raising `SandboxUnavailable`;
  - `remove(force=True, v=True)` being called in every path;
  - `reap_stale` removing only stale labelled containers;
  - no client being created at import time;
  - the 300-char guard;
  - the base64 argument order `[dir, slug, b64]`;
  - the profile kwargs, including `shm_size`, being passed through.

**Contract**: Run with the Django test runner. No Docker is needed.

### Success Criteria:

#### Automated Verification:

- Unit tests pass: `uv run python manage.py test challenges`
- Django check passes: `uv run python manage.py check`
- Real smoke run: `uv run python manage.py shell -c "from challenges import catalog, sandbox; print(sandbox.run_command(catalog.get('hello_world'), 'echo hello world'))"` shows `correct=True`

#### Manual Verification:

- `SANDBOX_RUN_PROFILE` reads as the table in Implementation Approach (single source, no duplicated flags elsewhere)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Verification sweep, abuse suite, and the cut

### Overview

Build the `verify_challenges` command, run it, cut failing challenges, and record the evidence.

### Changes Required:

#### 1. Management command

**File**: `challenges/management/commands/verify_challenges.py`

**Intent**: Prove every playable challenge works and every abuse is contained under the real profile. The command first calls `sandbox.reap_stale()` and then runs three stages.

- **(a) Example sweep.** Run each of the 42 examples (`all_main_set()`, so cut challenges are re-checked and reported, not gating) `--repeat` times (default 3) sequentially. The 9 challenges with a randomizer run `--repeat-randomized` times (default 20), because every run sees fresh random data and edge cases are probabilistic. Then run one pass at `--parallel` (default 8) with a thread pool.
  - With `--host-cpus N`, every sweep container gets `cpuset_cpus="0-<N-1>"` to emulate the event VM. This is harness-only and never added to `SANDBOX_RUN_PROFILE`.
  - Each `expected_failures` entry is also run once and must come back `correct=False`. An accepted entry on a non-excluded challenge fails the run.
  - A report-only **printable** probe runs `printf '%s\n'` of each challenge's expected output lines. It records whether just printing the answer is accepted, and it never gates or cuts. Challenges with a randomizer or a check are expected to reject it. The 20 static-output challenges are expected to accept it, per PRD FR-004 as reworded.
- **(b) Abuse suite.** Run on `hello_world` and assert that each scenario returns within 7 s wall time, `correct=False`, and that the container is gone:
  - fork bomb
  - CPU spin loop
  - 500 MB memory grab
  - disk fill of the cwd, of `/tmp` and of `/dev/shm`
  - output flood (`yes`), which must come back with the memory/output `error`, not `error_internal`
  - large legitimate-looking output (`seq 1 300000`, about 2 MB), which must come back with the memory/output or "output too large" `error`, not `error_internal`
  - `sleep 60`, which must come back with `timed_out=True`
  - network attempt (`/dev/tcp/1.1.1.1/80`)
  - write to `/usr/local/bin`
  - `id -u` output is `1000`, informational
- **(c) Canary.** While the fork bomb and the CPU spin run concurrently in background threads, run `hello_world`'s example 5×. Every canary run must be correct and finish in 6 s or less.

**Contract**:
- Flags: `--repeat N`, `--repeat-randomized N`, `--parallel N`, `--host-cpus N` (default: no pinning), `--only slug[,slug]`, `--skip-abuse`, `--json PATH`.
- Output is a table with these columns:
  - slug
  - pass count
  - sequential p50/p95 duration
  - parallel pass and duration
  - expected-failures result
  - printable (report-only)
  - `error_internal` count, reported separately
  - failure reason (first `error`/`timed_out`/`error_internal`)
- It ends with overall p50/p95 for the sequential and parallel runs and the `--host-cpus` value. Then comes a leak check: count of containers with label `bash-dash.sandbox`, before vs. after.
- Exit code is 0 only if all of the following hold for non-excluded challenges; otherwise it exits 1:
  - every run was correct;
  - no `error_internal` occurred;
  - no `expected_failures` entry was accepted;
  - the sequential and parallel p95 are both 4.0 s or less;
  - all abuse and canary assertions hold;
  - no containers leaked.

  An `error_internal` fails the run without making the challenge a cut candidate (see §2).

#### 2. Cut criteria and cut list

**File**: `challenges/excluded.yaml`

**Intent**: Record every challenge that fails the sweep, with a reason taken from the harness output. The cut rule has three conditions:
- The verifier says no: the example comes back `correct=False` with `error` set, or with `timed_out=True`, in any sequential or parallel run. An `error_internal` is infrastructure, not the challenge. It fails the run (see §1), but it is investigated and re-run, never cut.
- Its sequential p95 or its parallel p95 exceeds 4.0 s. That leaves no margin inside the 5 s in-container budget under load. Judge the parallel p95 with `--host-cpus` set to the assumed event VM core count (2 until F-02 settles the VM).
- An `expected_failures` entry is accepted as correct. The verification is broken, so the challenge is cut.

The printable probe never cuts (see §1).

These cuts come from the dev host with emulated cores. The sweep must be re-run on the event VM as part of F-02, and any new failure there is cut the same way.

Cut, never fix, per PRD Non-Goals. The exception is a failure caused by our own profile that a profile change can fix without weakening a guardrail, for example tmpfs `exec` or the size limit. That goes back into `SANDBOX_RUN_PROFILE`, and the whole sweep is re-run.

**Contract**: `slug: "<reason>"` entries. After this, `main_set()` returns only passing challenges.

#### 3. Integration tests (Docker-gated)

**File**: `challenges/tests/test_sandbox_integration.py`

**Intent**: Add three fast real-container tests: the `hello_world` example is correct; the first `expected_failures` entry of a randomized challenge (e.g. `sum_all_numbers`, which defeats a bare `echo`) is incorrect; and `sleep 60` returns `correct=False` with `timed_out=True` within 7 s wall time. runcmd's own 5 s timeout normally fires before the host's 6 s one, and its "timed out executing command" is mapped to `timed_out=True`. The host-timeout path is covered by the fake-client unit test. They are skipped with a clear reason when the Docker socket or image is unavailable.

**Contract**: Uses `unittest.skipUnless`, based on a helper that pings Docker and checks the image exists.

#### 4. Evidence and change notes

**File**: `context/changes/sandbox-image-and-task-cut/verification.md`, `context/changes/sandbox-image-and-task-cut/change.md`

**Intent**: Paste the final sweep table, including the report-only printable column and the count of challenges that accept a printed answer. Add:
- the latency summary, sequential and parallel, with the `--host-cpus` value (this feeds S-01's "≈1 s at concurrency" unknown and its concurrency cap);
- the abuse results;
- the cut list;
- the host, arch and Docker version it ran on.

State explicitly that the sweep must be re-run on the event VM in F-02. Add the answer to PRD OQ 4 in the `change.md` Notes.

**Contract**: The verification file has a header and date plus three sections: Sweep (including the Printable column), Abuse, Cut. It ends with a "Re-run on event VM (F-02)" note.

### Success Criteria:

#### Automated Verification:

- Full sweep green after the cut: `uv run python manage.py verify_challenges` exits 0
- Emulated event-VM sweep green: `uv run python manage.py verify_challenges --host-cpus 2 --skip-abuse` exits 0
- All tests pass, with the integration tests not skipped locally: `uv run python manage.py test challenges`
- No leaked sandbox containers: `docker ps -aq --filter label=bash-dash.sandbox` prints nothing
- Excluded list is valid: `uv run python manage.py shell -c "from challenges import catalog; print(len(catalog.main_set()))"` prints 42 minus the number of cuts

#### Manual Verification:

- Review `excluded.yaml` reasons: each cut is a real incompatibility, not a flaky run (re-run `--only <slug> --repeat 10` for any borderline one)
- `verification.md` has the Printable column and the "Re-run on event VM (F-02)" note
- While `verify_challenges` runs, the host stays responsive (`docker stats` shows sandbox containers capped at ~0.5 CPU / 100 MB)
- Playable-set size and ordering still make a sensible 5-minute game (first ~15 challenges are intact)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- **Catalog:** count, order, exclusion filtering, typo guard, `dir` defaulting.
- **Runner** (fake client): JSON parse, runcmd-timeout → `timed_out`, OOM and oversized-output → distinct `error`, internal-error mapping, host timeout path, `SandboxUnavailable`, lazy client, `reap_stale`, always-remove, 300-char guard, argument encoding, profile passthrough (incl. `shm_size`).

### Integration Tests:

- **Docker-gated tests** in the Django suite: correct, incorrect (an `expected_failures` entry is rejected), long-running command ends within 7 s with `timed_out=True`.
- **`verify_challenges`:** the exhaustive sweep plus abuse and canary. It is the regression gate for any future profile change.

### Manual Testing Steps:

1. Run `sandbox/build.sh`, then `uv run python manage.py verify_challenges --json /tmp/sweep.json`, then again with `--host-cpus 2 --skip-abuse`.
2. In a second terminal, watch `docker stats` during the abuse stage and confirm the CPU and memory caps hold and the host stays usable.
3. For each cut challenge, re-run `--only <slug> --repeat 10` to confirm it is not flaky.
4. Confirm `docker ps -a` and `docker volume ls -f dangling=true` show nothing new afterwards.

## Performance Considerations

Each command costs one container create, start, wait and remove. The sweep records sequential and concurrency-8 p50/p95, which is the first real measurement of the PRD's "≈1 s per command" assumption. S-01 will size its concurrency cap from it. `find_primes` is the expected slowest (measured during plan review: about 0.86 s per run at 0.5 CPU, 3.85 s at 0.125 CPU, and it runs twice). The 4.0 s p95 cut threshold applies to both the sequential and the parallel stage and guards the 5 s in-container budget. `--cpus 0.5` limits each container, not the host, so S-01's concurrency cap (about 2 × host cores) is what protects the host in aggregate. Dev-host numbers do not transfer to the event VM, so F-02 must re-run the sweep there.

## Migration Notes

None. There is no data, and this is the first app in the project.

## References

- Roadmap: `context/foundation/roadmap.md` (F-01)
- PRD: `context/foundation/prd.md` (NFR command isolation, FR-004, Non-Goals, OQ 4)
- Upstream analysis: `context/foundation/idea.md` §2.3–2.4, §5.3
- Upstream runner: `~/src/cmdchallenge/cmdchallenge/internal/challenge/runner.go:85-167`
- Upstream in-container logic: `~/src/cmdchallenge/cmdchallenge/internal/runcmd/runcmd.go:195-226`, `internal/challenge/checks.go:33-54`, `internal/challenge/randomizers.go:23-41`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Vendor the sandbox and build the image

#### Automated

- [ ] 1.1 Image builds: `sandbox/build.sh` exits 0
- [ ] 1.2 Static binary: `file /usr/local/bin/runcmd` reports "statically linked"
- [ ] 1.3 Hardened hello_world passes with full docker run flags
- [ ] 1.4 A file-writing challenge (create_file) passes the same way
- [ ] 1.5 Django still boots: `uv run python manage.py check`

#### Manual

- [ ] 1.6 `sandbox/README.md` and `sandbox/LICENSE` carry the upstream copyright and commit

### Phase 2: Challenge catalog and sandbox runner

#### Automated

- [ ] 2.1 Unit tests pass: `uv run python manage.py test challenges`
- [ ] 2.2 Django check passes: `uv run python manage.py check`
- [ ] 2.3 Real smoke run via `manage.py shell` shows `correct=True`

#### Manual

- [ ] 2.4 `SANDBOX_RUN_PROFILE` matches the hardening table (single source)

### Phase 3: Verification sweep, abuse suite, and the cut

#### Automated

- [ ] 3.1 Full sweep green after the cut: `uv run python manage.py verify_challenges` exits 0
- [ ] 3.2 Emulated event-VM sweep green: `verify_challenges --host-cpus 2 --skip-abuse` exits 0
- [ ] 3.3 All tests pass, integration tests not skipped locally
- [ ] 3.4 No leaked sandbox containers
- [ ] 3.5 Excluded list is valid; `main_set()` size = 42 − cuts

#### Manual

- [ ] 3.6 Each cut in `excluded.yaml` is a real incompatibility, not flakiness
- [ ] 3.7 `verification.md` has the Printable column and the F-02 VM re-run note
- [ ] 3.8 Host stays responsive; `docker stats` shows caps holding
- [ ] 3.9 Playable set still makes a sensible 5-minute game

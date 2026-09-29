# Sandbox Image and Task Cut — Plan Brief

> Full plan: `context/changes/sandbox-image-and-task-cut/plan.md`

## What & Why

We are building the hardened sandbox image, vendored from cmdchallenge, that will execute every player command. We then prove, under the exact production hardening, which of the 42 main-set challenges still work and cut the rest. This is roadmap F-01. S-01 (the north star) cannot start without it, and finding cuts late would change the game's scope at the last minute. It resolves PRD Open Question 4.

## Starting Point

bash-dash is a bare Django 6.1 scaffold with no apps or tests. Upstream cmdchallenge (a local clone at `~/src/cmdchallenge`, commit `09a3d7ad`) already does all verification inside the container and prints a JSON verdict. Its container launch has no pids, CPU or cap limits, and it leaks containers. Its Go test harness no longer compiles.

## Desired End State

- `sandbox/build.sh` builds `bash-dash-sandbox:latest`.
- The Django app `challenges` offers `catalog.main_set()` and `sandbox.run_command()`, and S-01 calls both unchanged.
- `manage.py verify_challenges` runs every example (3× sequentially, 20× for randomized challenges, plus concurrency 8, optionally pinned to N cores with `--host-cpus` to emulate the event VM), an abuse suite (fork bomb, CPU, memory, disk fill incl. `/dev/shm`, output flood, large output, network, sleep) and a canary. It exits 0.
- Failing challenges are listed with reasons in `challenges/excluded.yaml`.
- Latency numbers, the cut list and a report-only "printable" column (does just printing the answer pass?) are recorded in `verification.md`, with a note that the sweep must be re-run on the event VM in F-02.

## Key Decisions Made

These started as planner defaults. They were challenged in the plan review (`reviews/plan-review.md`, 2026-09-29), and the user accepted the review's resolutions, which are folded in below.

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Harness language | Python management command, not the upstream Go tests | Go tests don't compile, there's no Go toolchain, and the harness must exercise the exact runner S-01 will use |
| Writable fixtures vs read-only rootfs | Read-only rootfs + size-capped tmpfs `/var/challenges`, filled by an entrypoint copying from `/opt/challenges` | 21/42 challenges write to cwd; tmpfs is memory-charged, so disk fill cannot hit the host disk and there are no volumes to leak |
| Container user | Non-root `player` (uid 1000), fixtures chowned | Cheap defense in depth on a host whose app holds docker.sock |
| Capabilities | `cap_drop=ALL` + `no-new-privileges` | Research found no challenge needing caps |
| Limits | 100 MB RAM (no swap), 64 pids, 0.5 CPU, `GOMAXPROCS=1`, `shm_size` 1 MB, json-file log max 1 MB | Covers fork bomb, CPU burn, memory, `/dev/shm` fill, and log flood; 0.5 CPU is per container, so S-01's concurrency cap protects the host in aggregate |
| runcmd build | `CGO_ENABLED=0` static binary | Avoids a glibc mismatch between the Debian builder and the Ubuntu 22.04 runtime; sqlite is unused in `-cmd` mode |
| How cuts are recorded | `challenges/excluded.yaml` (`slug: reason`); upstream YAML untouched | Keeps the vendored code pristine, and each cut is documented |
| Cut rule | Verifier "no" or timeout in any run, sequential or parallel p95 > 4.0 s (parallel judged with `--host-cpus`), or an accepted `expected_failures`; `error_internal` fails the run but never cuts; the printable probe never cuts | Cut, don't fix (PRD Non-Goals); 4 s leaves margin in the 5 s in-container budget under event-like load |
| Architecture | Host arch (amd64) by default, `BUILD_ARCH` override | The VM arch is still open (OQ 9); one arch suffices |

## Scope

**In scope:**
- Vendored Go module and license
- Trimmed Dockerfile, entrypoint and build script
- The `challenges` app (catalog, runner, unit tests, Docker-gated integration tests)
- `verify_challenges` with the abuse suite and canary
- The cut list and the verification log

**Out of scope:**
- Game models, views and sessions, plus the S-01 rate limit and concurrency cap
- Fixing challenges
- The `12days`/`oops` sets
- gVisor and userns-remap
- A multi-arch registry push
- CI

## Architecture / Approach

Django calls `sandbox.run_command(challenge, cmd)`, which uses the Docker SDK to run `bash-dash-sandbox` with the hardening profile. The command is `sandbox-entry <dir> <slug> <b64>`. In the container, sandbox-entry copies the fixture into tmpfs, `cd`s there and execs `runcmd -cmd`. runcmd runs bash (5 s limit), the randomizers and the checks, then prints JSON. Python waits at most 6 s, reads the last stdout line, and always removes the container. A single `SANDBOX_RUN_PROFILE` dict defines the hardening for both the harness and the game. runcmd's own timeout maps to `timed_out`; OOM kills and oversized output map to distinct player-facing errors; Docker failures before the container exists raise `SandboxUnavailable`. `reap_stale()` removes orphaned containers.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Vendor + image | `sandbox/` and a hardened image; hello_world and create_file pass by hand | Static build or tmpfs `exec`/ownership quirks |
| 2. Catalog + runner | `challenges` app with typed runner and unit tests | Timeout and cleanup edge cases in docker-py |
| 3. Sweep + cut | `verify_challenges`, abuse suite, `excluded.yaml`, `verification.md` | Dev-host timing not matching the event VM; mitigated by `--host-cpus` and the F-02 re-run |

**Prerequisites:** Docker on the dev host (present: 29.8.1, amd64), network for the image build, the `~/src/cmdchallenge` clone.
**Estimated effort:** About 1 focused session across 3 phases, which fits the 2026-10-03 deadline.

## Open Risks & Assumptions

- The event VM core count is assumed to be 2 for `--host-cpus` until F-02 settles the VM.
- If the target VM turns out to be arm64 (F-02), rebuild with `BUILD_ARCH=arm64` and re-run the sweep there.
- Latency on the dev machine differs from the VM. Re-running `verify_challenges` on the VM is required in F-02.
- If `CGO_ENABLED=0` fails to build, the fallback is the `golang:1.24-bullseye` builder.
- Kernel and host defenses (seccomp and AppArmor defaults) are assumed to be on, as on the dev host.

## Success Criteria (Summary)

- One command builds the image, and one command proves every playable challenge passes under production hardening.
- A fork bomb, CPU burn, memory grab, disk fill or output flood from one player ends within about 6 s, and a concurrent player's command still completes correctly within 6 s.
- The playable challenge list and the reasons for every cut are explicit, answering PRD OQ 4. Which challenges accept a printed answer is documented (PRD FR-004 as reworded).

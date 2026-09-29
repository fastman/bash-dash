# Sandbox Image and Task Cut — Plan Brief

> Full plan: `context/changes/sandbox-image-and-task-cut/plan.md`

## What & Why

We are building the hardened sandbox image, vendored from cmdchallenge, that will execute every player command. We then prove, under the exact production hardening, which of the 42 main-set challenges still work and cut the rest. This is roadmap F-01. S-01 (the north star) cannot start without it, and finding cuts late would change the game's scope at the last minute. It resolves PRD Open Question 4.

## Starting Point

bash-dash is a bare Django 6.1 scaffold with no apps or tests. Upstream cmdchallenge (a local clone at `~/src/cmdchallenge`, commit `09a3d7ad`) already does all verification inside the container and prints a JSON verdict. Its container launch has no pids, CPU or cap limits, and it leaks containers. Its Go test harness no longer compiles.

## Desired End State

- `sandbox/build.sh` builds `bash-dash-sandbox:latest`.
- The Django app `challenges` offers `catalog.main_set()` and `sandbox.run_command()`, and S-01 calls both unchanged.
- `manage.py verify_challenges` runs every example (3× sequentially plus concurrency 8), an abuse suite (fork bomb, CPU, memory, disk fill, output flood, network, sleep) and a canary. It exits 0.
- Failing challenges are listed with reasons in `challenges/excluded.yaml`.
- Latency numbers and the cut list are recorded in `verification.md`.

## Key Decisions Made

These were made as planner defaults, because this ran as an unattended background job with no interactive questioning. Each follows the research-backed recommendation, and the user can override any of them.

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Harness language | Python management command, not the upstream Go tests | Go tests don't compile, there's no Go toolchain, and the harness must exercise the exact runner S-01 will use |
| Writable fixtures vs read-only rootfs | Read-only rootfs + size-capped tmpfs `/var/challenges`, filled by an entrypoint copying from `/opt/challenges` | 21/42 challenges write to cwd; tmpfs is memory-charged, so disk fill cannot hit the host disk and there are no volumes to leak |
| Container user | Non-root `player` (uid 1000), fixtures chowned | Cheap defense in depth on a host whose app holds docker.sock |
| Capabilities | `cap_drop=ALL` + `no-new-privileges` | Research found no challenge needing caps |
| Limits | 100 MB RAM (no swap), 64 pids, 0.5 CPU, `GOMAXPROCS=1`, json-file log max 1 MB | Covers fork bomb, CPU burn, memory, and log flood |
| runcmd build | `CGO_ENABLED=0` static binary | Avoids a glibc mismatch between the Debian builder and the Ubuntu 22.04 runtime; sqlite is unused in `-cmd` mode |
| How cuts are recorded | `challenges/excluded.yaml` (`slug: reason`); upstream YAML untouched | Keeps the vendored code pristine, and each cut is documented |
| Cut rule | Any failed run, sequential p95 > 4.0 s, or an accepted `expected_failures` | Cut, don't fix (PRD Non-Goals); 4 s leaves margin in the 5 s in-container budget |
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

Django calls `sandbox.run_command(challenge, cmd)`, which uses the Docker SDK to run `bash-dash-sandbox` with the hardening profile. The command is `sandbox-entry <dir> <slug> <b64>`. In the container, sandbox-entry copies the fixture into tmpfs, `cd`s there and execs `runcmd -cmd`. runcmd runs bash (5 s limit), the randomizers and the checks, then prints JSON. Python waits at most 6 s, reads the last stdout line, and always removes the container. A single `SANDBOX_RUN_PROFILE` dict defines the hardening for both the harness and the game.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Vendor + image | `sandbox/` and a hardened image; hello_world and create_file pass by hand | Static build or tmpfs `exec`/ownership quirks |
| 2. Catalog + runner | `challenges` app with typed runner and unit tests | Timeout and cleanup edge cases in docker-py |
| 3. Sweep + cut | `verify_challenges`, abuse suite, `excluded.yaml`, `verification.md` | Flaky timing near the 5 s budget causing wrong cuts |

**Prerequisites:** Docker on the dev host (present: 29.8.1, amd64), network for the image build, the `~/src/cmdchallenge` clone.
**Estimated effort:** About 1 focused session across 3 phases, which fits the 2026-10-03 deadline.

## Open Risks & Assumptions

- The planner-default decisions above were not confirmed interactively.
- If the target VM turns out to be arm64 (F-02), rebuild with `BUILD_ARCH=arm64` and re-run the sweep there.
- Latency on the dev machine may differ from the VM. Re-run `verify_challenges` on the VM as part of F-02.
- If `CGO_ENABLED=0` fails to build, the fallback is the `golang:1.24-bullseye` builder.
- Kernel and host defenses (seccomp and AppArmor defaults) are assumed to be on, as on the dev host.

## Success Criteria (Summary)

- One command builds the image, and one command proves every playable challenge passes under production hardening.
- A fork bomb, CPU burn, memory grab, disk fill or output flood from one player ends within about 6 s and does not slow a concurrent player.
- The playable challenge list and the reasons for every cut are explicit, answering PRD OQ 4.

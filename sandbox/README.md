# sandbox — vendored cmdchallenge verifier

This directory vendors the Go verification sandbox from
[cmdchallenge](https://gitlab.com/jarv/cmdchallenge), used by bash-dash to run
and check player commands inside a hardened Docker container.

- Upstream: https://gitlab.com/jarv/cmdchallenge (subdirectory `cmdchallenge/`)
- Commit: `09a3d7ad1d6ca78bc3ad90c5bf7dda85b1087a42`
- License: MIT — Copyright (c) 2017-2020 john@jarv.org (see `LICENSE`, copied
  verbatim from the upstream repository root)

## What was vendored

`cmd/runcmd/`, `internal/` (all packages), `var/`, `go.mod`, `go.sum` — unchanged
except for the one Go patch listed under "Local modifications".
`internal/challenge/challenges.yaml` is the single source of truth for
challenges; the Python catalog (`challenges/catalog.py`) reads the same file.

## What was dropped

`cmd/oops`, `cmd/submissions`, `cmd/test`, `Dockerfile-cmd-no-bin`, `test.txt`.

## Local modifications

### Go patch: PID 1 hardening (`cmd/runcmd`)

runcmd runs as PID 1 of the sandbox container with the same uid as the
player's command, so upstream's runcmd lets the player write forged JSON to
`/proc/1/fd/1` or `kill -TERM 1`. (The implementation review found this as F1;
the user approved this Go change, which overrides the plan's "no Go changes"
rule.) The patch is kept minimal:

- `cmd/runcmd/harden_linux.go` (new) — `hardenPID1()`:
  `prctl(PR_SET_DUMPABLE, 0)` makes `/proc/1/{fd,environ,mem,…}` root-owned,
  so a same-uid process without `CAP_SYS_PTRACE` can't open them. Children
  become dumpable again on `execve`, so the player's bash is unaffected. It
  also installs never-drained `signal.Notify` handlers for SIGTERM, SIGINT,
  SIGHUP, SIGQUIT, SIGUSR1 and SIGUSR2, so these signals are delivered and
  dropped rather than killing PID 1. The patch catches them instead of using
  `signal.Ignore`, because an ignored disposition would be inherited by the
  player's bash.
- `cmd/runcmd/harden_other.go` (new) — no-op for non-Linux builds.
- `cmd/runcmd/runcmd.go` — one added line: `hardenPID1()` at the top of `main()`.

The host (`challenges/sandbox.py`) also trusts a verdict only when stdout is
exactly one non-empty line; that check is the backstop.

### Local files

- `Dockerfile` — derived from upstream `Dockerfile-cmd`: builds only `runcmd`,
  statically (`CGO_ENABLED=0`); no `oops` binary; `docker/dockerfile:1` syntax;
  non-root `player` user (uid/gid 1000); fixtures stored at `/opt/challenges`
  owned by `player`; `sandbox-entry` entrypoint.
- `sandbox-entry.sh` — copies `/opt/challenges/<dir>` into the `/var/challenges`
  tmpfs, `cd`s there and execs `runcmd -cmd -slug <slug> <base64-cmd>`. Exits
  64 on a usage error and 65 on a missing fixture dir, both outside the codes
  bash and runcmd use.
- `build.sh` — builds `bash-dash-sandbox:latest` (`BUILD_ARCH`, `SANDBOX_IMAGE`
  env overrides).

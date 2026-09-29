# sandbox — vendored cmdchallenge verifier

This directory vendors the Go verification sandbox from
[cmdchallenge](https://gitlab.com/jarv/cmdchallenge), used by bash-dash to run
and check player commands inside a hardened Docker container.

- Upstream: https://gitlab.com/jarv/cmdchallenge (subdirectory `cmdchallenge/`)
- Commit: `09a3d7ad1d6ca78bc3ad90c5bf7dda85b1087a42`
- License: MIT — Copyright (c) 2017-2020 john@jarv.org (see `LICENSE`, copied
  verbatim from the upstream repository root)

## What was vendored

`cmd/runcmd/`, `internal/` (all packages), `var/`, `go.mod`, `go.sum` — unchanged.
`internal/challenge/challenges.yaml` is the single source of truth for
challenges; the Python catalog (`challenges/catalog.py`) reads the same file.

## What was dropped

`cmd/oops`, `cmd/submissions`, `cmd/test`, `Dockerfile-cmd-no-bin`, `test.txt`.

## Local modifications

Go sources are unmodified. Local files only:

- `Dockerfile` — derived from upstream `Dockerfile-cmd`: builds only `runcmd`,
  statically (`CGO_ENABLED=0`); no `oops` binary; `docker/dockerfile:1` syntax;
  non-root `player` user (uid/gid 1000); fixtures stored at `/opt/challenges`
  owned by `player`; `sandbox-entry` entrypoint.
- `sandbox-entry.sh` — copies `/opt/challenges/<dir>` into the `/var/challenges`
  tmpfs, `cd`s there and execs `runcmd -cmd -slug <slug> <base64-cmd>`.
- `build.sh` — builds `bash-dash-sandbox:latest` (`BUILD_ARCH`, `SANDBOX_IMAGE`
  env overrides).

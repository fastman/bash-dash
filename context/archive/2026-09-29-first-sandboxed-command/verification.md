# Verification: first sandboxed command (S-01)

- **Date:** 2026-09-29
- **Host:** dev laptop, Linux 7.0.0-31-generic, x86_64, Intel i5-1145G7, 8 logical CPUs, 14 GiB RAM (same host as F-01)
- **Docker:** 29.8.1; docker-py 7.2.0; Django 6.1.1
- **Image:** `bash-dash-sandbox:latest` (F-01 build, unchanged)
- **DB:** SQLite file `db.sqlite3` with `journal_mode=WAL`, `synchronous=NORMAL`, `transaction_mode=IMMEDIATE`, `timeout=20`
- **Cap:** `SANDBOX_MAX_CONCURRENT=8` (default), `SANDBOX_QUEUE_TIMEOUT_S=10`, docker pool size 10
- **Pinning:** none. `bench_game` drives `game.services`, which never passes `host_overrides`, so `--host-cpus` pinning does not apply. The F-02 event-VM re-run provides the real-CPU numbers.

## How the benchmark works

`uv run python manage.py bench_game` starts N threads. Each thread is one player: `start_game('bench-<i>')`, then `--commands` submits through `services.submit_command` with **no think time** between them. The `typical` mix alternates a wrong answer (`echo bench-wrong-answer`) with the current challenge's correct example. `with-abuse` makes player 0 send `sleep 60` every time. Timing is per submit wall time, which includes semaphore queueing, the sandbox run and the SQLite writes.

This is a worst case for the "~15 players" unknown: real players read, think and type for several seconds between commands. N players firing back-to-back keep the cap-8 semaphore saturated for the whole run.

## Results

| Run | Submits | p50 | p95 | max | Statuses | Lock errors | Leaked | Elapsed | Exit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `--players 15` (typical) | 150 | 0.549 s | 0.658 s | 0.770 s | ran: 150 | 0 | 0 | 6.1 s | 0 |
| `--players 15 --mix with-abuse`, all | 150 | 0.597 s | 5.161 s | 5.572 s | ran: 150 | 0 | 0 | 52.6 s | 0 |
| ↳ 14 non-abusers | 140 | 0.594 s | 0.685 s | 0.830 s | | | | | |
| ↳ abuser (`sleep 60`) | 10 | 5.186 s | 5.465 s | 5.572 s | | | | | |
| `--players 30` (typical) | 300 | 1.110 s | 1.226 s | 2.425 s | ran: 300 | 0 | 0 | 11.6 s | 0 |

Throughput at cap 8 is ~25 runs/s (150 / 6.1 s, 300 / 11.6 s). That is ~0.3 s of service time per run with 8 in flight, against F-01's ~0.14 s sequential. With saturated back-to-back load, most of the p50 is queue wait on the semaphore: 15 players / 25 runs/s ≈ 0.6 s, 30 / 25 ≈ 1.2 s, which matches the measurements.

The live checks through `runserver` (Phase 3) measured ~0.15–0.21 s per command end-to-end for a single player, and 5.22 s for a fork bomb or `sleep 60` (timed out, counted).

## Verdict on the "~1 s at ~15 concurrent players" unknown

**Yes.** With 15 players submitting continuously (well above real event load), p95 is 0.66 s. One continuous abuser holds a slot for ~5.2 s per command, and the other 14 players' p95 moves only to 0.69 s. The NFR (≤ ~6 s per command, ~1 s typical) holds. Doubling to 30 continuous players reaches ~1.1–1.2 s, driven by queueing and not by errors. That is still inside "~1 s accepted", and real players with think time will load the host much less. There were zero `database is locked` errors in all runs.

## Concurrency contract for F-02

- **Per process:** the semaphore (`SANDBOX_MAX_CONCURRENT`, env `BASHDASH_SANDBOX_CONCURRENCY`) and the docker client (pool = cap + 2) are per process. **Total sandbox concurrency = worker processes × cap.**
- **Recommended:** one process with threads, e.g. `gunicorn config.wsgi --workers 1 --threads 16`. Threads must be ≥ cap + a few, so page loads are not starved by requests waiting on the semaphore. With more processes, scale the cap down so processes × cap stays ≈ 8 on the measured host (re-measure on the event VM).
- **Timeouts:** the worst-case request is queue 10 s + run 6 s + overhead ≈ 17 s. The proxy/WSGI timeout must be above that (≥ 30 s; `play.js` aborts at 25 s).
- **SQLite:** WAL is on. Back up with SQLite's online backup (`sqlite3 db.sqlite3 ".backup /path/backup.sqlite3"`), never `cp`. `db.sqlite3-wal` and `db.sqlite3-shm` live next to the DB. `ATOMIC_REQUESTS` must stay `False`.
- **Reaping:** the game reaps orphans once per process, only containers older than 30 s (`GAME_REAP_MIN_AGE_S`), so that is safe during play. **`verify_challenges` reaps with `min_age_s=0`, so it must not run on the event host while games are live**, because it would delete in-flight game containers.
- **Hosts:** set `BASHDASH_ALLOWED_HOSTS` to the real hostname.

## To do on the event VM (F-02)

Re-run `bench_game --players 15`, `--players 15 --mix with-abuse` and `--players 30` on the event VM and add a row per run above. If typical p95 at 15 players exceeds ~1 s there, lower the per-command cost first (it is queue-dominated) or raise the cap if the VM has CPU headroom.

## Manual checks pending (need a human)

- Phase 3: playing at phone width in a browser, with the visual layout of the verdict/output, output scrolling inside its box, and the input keeping the command after "sandbox unavailable". The server side of each was verified from the shell against the live dev server.
- Phase 4: a real phone over LAN (`BASHDASH_ALLOWED_HOSTS=<lan-ip> uv run python manage.py runserver 0.0.0.0:8000`): no autocapitalize/autocorrect, the "send" key submits, and the output is readable.

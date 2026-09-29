# Verification: sandbox image and task cut (F-01)

- **Date:** 2026-09-29
- **Host:** Ubuntu 26.04.1 LTS, Linux 7.0.0-31-generic, x86_64 (amd64), Intel i5-1145G7, 8 logical CPUs
- **Docker:** 29.8.1, runc, cgroup v2, default seccomp/AppArmor
- **Image:** `bash-dash-sandbox:latest` built by `sandbox/build.sh` (static `runcmd`, `CGO_ENABLED=0`; no builder fallback needed)
- **Profile:** `challenges/sandbox.py::SANDBOX_RUN_PROFILE` (network none, 100m mem/swap, 64 pids, 0.5 CPU, cap_drop ALL, no-new-privileges, uid 1000, read-only rootfs, tmpfs `/var/challenges` 16m exec + `/tmp` 16m, shm 1m, GOMAXPROCS=1, json-file 1m, label `bash-dash.sandbox`)
- **Commands:** `uv run python manage.py verify_challenges` (defaults: `--repeat 3 --repeat-randomized 20 --parallel 8`, unpinned) → exit 0, 104 s; `uv run python manage.py verify_challenges --host-cpus 2 --skip-abuse` → exit 0

## Sweep

Unpinned run (full, with abuse). `pass` counts sequential + 1 parallel run. `(r)` = randomized (20 sequential runs). `exp-fail`: `ok` = every `expected_failures` entry rejected, `n/a` = none defined. `print` (report-only, never cuts): `yes` = a bare `printf` of the expected lines is accepted, `no` = rejected, `long` = such a command exceeds the 300-char limit, so a player cannot do it either.

```
slug                                      pass seq p50 seq p95  par  par s exp-fail print int  reason
-----------------------------------------------------------------------------------------------------
hello_world                              4/4      0.13    0.14   ok   0.21       ok   yes   0  
current_working_directory                4/4      0.13    0.14   ok   0.29       ok   yes   0  
list_files (r)                          21/21     0.13    0.14   ok   0.29       ok    no   0  
print_file_contents                      4/4      0.14    0.14   ok   0.32      n/a  long   0  
last_lines                               4/4      0.13    0.14   ok   0.32      n/a  long   0  
create_file                              4/4      0.14    0.14   ok   0.35       ok    no   0  
create_directory                         4/4      0.14    0.14   ok   0.34       ok    no   0  
copy_file                                4/4      0.14    0.14   ok   0.35       ok    no   0  
move_file                                4/4      0.14    0.15   ok   0.28       ok    no   0  
create_symlink                           4/4      0.14    0.15   ok   0.29       ok    no   0  
delete_files                             4/4      0.14    0.14   ok   0.28       ok    no   0  
remove_files_with_extension              4/4      0.15    0.16   ok   0.28       ok    no   0  
find_string_in_a_file                    4/4      0.14    0.14   ok   0.27      n/a  long   0  
search_for_files_containing_string (r)  21/21     0.14    0.15   ok   0.33       ok    no   0  
search_for_files_by_extension            4/4      0.14    0.14   ok   0.27      n/a   yes   0  
search_for_string_in_files_recursive     4/4      0.14    0.15   ok   0.28      n/a   yes   0  
extract_ip_addresses                     4/4      0.13    0.14   ok   0.26      n/a   yes   0  
count_files (r)                         21/21     0.14    0.15   ok   0.26       ok    no   0  
simple_sort                              4/4      0.14    0.14   ok   0.28      n/a  long   0  
count_string_in_line (r)                21/21     0.14    0.15   ok   0.28       ok    no   0  
split_on_a_char                          4/4      0.14    0.15   ok   0.30      n/a   yes   0  
print_number_sequence                    4/4      0.14    0.15   ok   0.34      n/a  long   0  
replace_text_in_files                    4/4      0.14    0.15   ok   0.31       ok    no   0  
sum_all_numbers (r)                     21/21     0.14    0.15   ok   0.29       ok    no   0  
just_the_files                           4/4      0.14    0.16   ok   0.25      n/a   yes   0  
remove_extensions_from_files             4/4      0.14    0.16   ok   0.27       ok    no   0  
replace_spaces_in_filenames              4/4      0.14    0.16   ok   0.28      n/a  long   0  
dirs_containing_files_with_extension (r)  21/21     0.15    0.16   ok   0.32      n/a    no   0  
files_starting_with_a_number             4/4      0.14    0.15   ok   0.28      n/a  long   0  
print_nth_line                           4/4      0.14    0.14   ok   0.25      n/a   yes   0  
reverse_readme                           4/4      0.14    0.14   ok   0.34      n/a  long   0  
remove_duplicate_lines                   4/4      0.14    0.15   ok   0.34      n/a   yes   0  
find_primes (r)                         21/21     1.69    2.10   ok   1.63       ok    no   0  
print_common_lines                       4/4      0.14    0.14   ok   0.32      n/a   yes   0  
print_line_before                        4/4      0.14    0.14   ok   0.34      n/a  long   0  
print_files_if_different                 4/4      0.14    0.41   ok   0.28      n/a   yes   0  
nested_dirs (r)                         21/21     0.14    0.15   ok   0.28       ok    no   0  
find_tabs_in_a_file (r)                 21/21     0.14    0.15   ok   0.29       ok    no   0  
remove_files_without_extension           4/4      0.14    0.15   ok   0.26       ok    no   0  
remove_files_with_a_dash                 4/4      0.14    0.14   ok   0.25       ok    no   0  
print_sorted_by_key                      4/4      0.14    0.48   ok   0.20      n/a  long   0  
IPv4_listening_ports                     4/4      0.14    0.14   ok   0.17      n/a   yes   0  
(* = excluded, reported only; (r) = randomized)
```

Printable (report-only): **12/42** accept a printed answer; the other 10 static-output challenges cannot be answered that way within the 300-char limit (`long`); the 20 challenges with a randomizer (9) or a check (11) reject it (`no`), as expected.

### Latency

| Run | host-cpus | Sequential p50 / p95 (n) | Parallel ×8 p50 / p95 (n) | Slowest challenge |
| --- | --- | --- | --- | --- |
| full + abuse | unpinned | 0.14 s / 1.58 s (279) | 0.28 s / 0.35 s (42) | `find_primes` seq p95 2.10 s, parallel 1.63 s |
| sweep only (`--skip-abuse`) | 2 (`0-1`) | 0.14 s / 1.19 s (279) | 0.28 s / 0.39 s (42) | `find_primes` seq p95 1.42 s, parallel 1.23 s |

Durations are wall time per `run_command` (container create + start + run + remove). Every challenge except `find_primes` sits around 0.14 s sequentially and about 0.3 s at concurrency 8. `find_primes` is the only heavy challenge, at about 1.2–2.1 s. That is well under the 4.0 s cut threshold, and a borderline re-run (`--only find_primes --repeat 10 --repeat-randomized 10 --host-cpus 2`) passed 11/11 with p95 1.45 s. For S-01: a typical command costs about 0.15 s, and about 0.3 s under 8 concurrent commands.

## Abuse

All scenarios run on `hello_world`; each must return within 7 s, be incorrect, and leave no container.

```
abuse scenario                                 wall s contained  outcome
fork bomb                                        5.16       yes  timed_out
cpu spin                                         5.17       yes  timed_out
memory grab 500MB                                0.24       yes  Command used too much memory or output
disk fill cwd                                    0.14       yes  Output does not match expected lines
disk fill /tmp                                   0.14       yes  Output does not match expected lines
disk fill /dev/shm                               0.14       yes  Output does not match expected lines
output flood (yes)                               0.26       yes  Command used too much memory or output
large output (seq 1 300000)                      0.49       yes  Output too large (limit about 1 MB)
sleep 60                                         5.16       yes  timed_out
network attempt                                  0.14       yes  Output does not match expected lines
write /usr/local/bin                             0.14       yes  Output does not match expected lines
id -u (info)                                     0.15       yes  Output does not match expected lines [1000]
canary x5 under fork bomb + cpu spin             0.16       yes  5/5 correct
```

Spot checks (outputs of the same commands):
- disk fill: cwd stops at 16 MiB (tmpfs), `/tmp` at 16 MiB, and `/dev/shm` at 1 MiB (`shm_size`)
- `/usr/local/bin` write: `Read-only file system`
- `/dev/tcp/1.1.1.1/80`: `Network is unreachable`
- `id -u`: `1000`
- `docker stats` during a CPU spin: `cpu=50.06% mem=4.02MiB / 100MiB pids=4`; host load average stayed under 1

Leak check: 0 labelled containers before, 0 after, on both runs. `docker ps -aq --filter label=bash-dash.sandbox` is empty afterwards.

## Cut

**No challenges cut.** `challenges/excluded.yaml` is `{}` and `catalog.main_set()` returns all 42 challenges in upstream order.

No main-set challenge met any cut condition on this host:
- no verifier rejection or timeout in any sequential or parallel run
- no per-challenge p95 over 4.0 s (worst: `find_primes` at 2.10 s unpinned, 1.42 s pinned to 2 CPUs)
- no accepted `expected_failures` entry

There was no `error_internal` in any run.

## Re-run on event VM (F-02)

These results come from the dev host, using emulated cores (`--host-cpus 2`). They do **not** transfer to the event VM. As part of F-02, rebuild the image there (`BUILD_ARCH` if arm64), then run `uv run python manage.py verify_challenges` and `verify_challenges --host-cpus <vm cores> --skip-abuse`. Cut any new failure the same way, by adding it to `challenges/excluded.yaml` with the harness reason.

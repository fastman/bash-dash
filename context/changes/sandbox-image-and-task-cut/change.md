---
change_id: sandbox-image-and-task-cut
title: Sandbox image and task cut
status: implemented
created: 2026-09-29
updated: 2026-09-29
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

- **PRD OQ 4 ("Which of the 42 challenges do we cut?") — answer: none, on the dev host.** All 42 main-set
  challenges pass `verify_challenges` under the production hardening profile, unpinned and with `--host-cpus 2`
  (see `verification.md`). `challenges/excluded.yaml` is `{}`. This is provisional until the sweep is re-run on
  the event VM in F-02.
- Latency for S-01: about 0.14 s per command sequentially and about 0.3 s at concurrency 8. `find_primes` is the outlier at
  about 1.2–2.1 s.
- S-01 should call `challenges.sandbox.reap_stale()` at app startup.
- Deviation from the plan: the json-file 1 MB cap *rotates*, so a truncated runcmd line can be any size under 1 MB.
  "Unparsable output with container exit 0" therefore also maps to "Output too large" (the plan's ≥900 KB rule is kept).
  `run_command` also gained a harness-only `host_overrides` argument (it cannot replace profile keys) for `--host-cpus`.


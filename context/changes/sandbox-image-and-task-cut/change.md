---
change_id: sandbox-image-and-task-cut
title: Sandbox image and task cut
status: impl_reviewed
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
  `run_command` also gained a harness-only `host_overrides` argument (an allowlist of `cpuset_cpus`) for `--host-cpus`.
- The implementation review (F1–F9) was resolved with user-approved fixes, including a minimal Go patch that hardens runcmd as PID 1.
  See `plan.md` § Addendum and `reviews/impl-review.md`.
- **Carry-overs for S-01 (review F9):**
  - (a) `reap_stale` at startup races with in-flight runs if several workers or processes start it. Run it once, e.g. from a
    single startup hook or a lock, not per worker.
  - (b) docker-py's HTTP connection pool holds 10 connections. More than about 10 concurrent `run_command` calls through the
    shared client queue or warn, so size the pool or cap concurrency to match the worker count.
  - (c) `run_command` calls `images.get` on every command. This could be cached after the first success; the image only changes
    on deploy.
  - (d) `catalog.get(slug)` also returns excluded challenges. S-01 must serve challenges from `catalog.main_set()` and only use
    `get()` for slugs from that set.


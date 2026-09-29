"""Run every main-set challenge's example plus an abuse suite under the real profile.

Exit 0 only if every non-excluded challenge passes and every abuse scenario is
contained. See context/changes/sandbox-image-and-task-cut/plan.md (Phase 3).
"""

import dataclasses
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand, CommandError

from challenges import catalog, sandbox, verify

ABUSE_WALL_LIMIT_S = 7.0
CANARY_RUNS = 5
CANARY_LIMIT_S = 6.0
TOO_MUCH = (sandbox.MEMORY_ERROR, sandbox.TOO_LARGE_ERROR)


def _no_marker(marker):
    def check(r):
        return f'{marker!r} appeared in output' if marker in r.output else None
    return check


# (name, command, extra check returning an error string or None)
ABUSE_SCENARIOS = [
    ('fork bomb', ':(){ :|:& };:', None),
    ('cpu spin', 'while :; do :; done', None),
    ('memory grab 500MB', 'head -c 500M /dev/zero | tail', None),
    ('disk fill cwd', 'dd if=/dev/zero of=fill bs=1M count=200; ls -la', None),
    ('disk fill /tmp', 'dd if=/dev/zero of=/tmp/fill bs=1M count=200; ls -la /tmp', None),
    ('disk fill /dev/shm', 'dd if=/dev/zero of=/dev/shm/fill bs=1M count=200; ls -la /dev/shm', None),
    ('output flood (yes)', 'yes',
     lambda r: None if r.error == sandbox.MEMORY_ERROR else f'expected memory/output error, got {r!r}'),
    ('large output (seq 1 300000)', 'seq 1 300000',
     lambda r: None if r.error in TOO_MUCH else f'expected memory/output or too-large error, got {r!r}'),
    ('sleep 60', 'sleep 60', lambda r: None if r.timed_out else 'expected timed_out=True'),
    ('network attempt', '(exec 3<>/dev/tcp/1.1.1.1/80) && echo CONNECTED', _no_marker('CONNECTED')),
    ('write /usr/local/bin', 'echo x > /usr/local/bin/pwn && echo WROTE', _no_marker('WROTE')),
    ('id -u (info)', 'id -u', None),
]


class Command(BaseCommand):
    help = 'Verify every main-set challenge and the abuse guardrails in the sandbox.'

    def add_arguments(self, parser):
        parser.add_argument('--repeat', type=int, default=3)
        parser.add_argument('--repeat-randomized', type=int, default=20)
        parser.add_argument('--parallel', type=int, default=8)
        parser.add_argument('--host-cpus', type=int, default=None,
                            help='Pin sweep containers to CPUs 0..N-1 (emulate the event VM).')
        parser.add_argument('--only', default='', help='Comma-separated slugs.')
        parser.add_argument('--skip-abuse', action='store_true')
        parser.add_argument('--json', dest='json_path', default=None)

    # ---- helpers -------------------------------------------------------

    def _label_count(self):
        client = sandbox._get_client()
        return len(client.containers.list(all=True, filters={'label': sandbox.SANDBOX_LABEL}))

    def _run(self, ch, command):
        return sandbox.run_command(ch, command, host_overrides=self.overrides)

    # ---- stages --------------------------------------------------------

    def _sweep(self, challenges, opts):
        excluded = catalog.excluded()
        randomized = verify.randomized_slugs()
        reports = {}
        for ch in challenges:
            n = opts['repeat_randomized'] if ch.slug in randomized else opts['repeat']
            seq = [self._run(ch, ch.example) for _ in range(n)]
            efs = {cmd: self._run(ch, cmd) for cmd in ch.expected_failures}
            probe_cmd = verify.printable_command(ch)
            if probe_cmd is None:
                printable = 'long'
            else:
                printable = 'yes' if self._run(ch, probe_cmd).correct else 'no'
            reports[ch.slug] = verify.ChallengeReport(
                slug=ch.slug, excluded=ch.slug in excluded, sequential=seq, parallel=None,
                expected_failures=efs, printable=printable,
                extra={'randomized': ch.slug in randomized},
            )
            r = reports[ch.slug]
            self.stderr.write(f'  {ch.slug}: {sum(x.correct for x in seq)}/{n} p95 {r.seq_p95:.2f}s')

        self.stderr.write(f'Parallel pass (concurrency {opts["parallel"]})...')
        with ThreadPoolExecutor(max_workers=opts['parallel']) as pool:
            results = list(pool.map(lambda c: self._run(c, c.example), challenges))
        for ch, res in zip(challenges, results):
            reports[ch.slug].parallel = res
        return [reports[c.slug] for c in challenges]

    def _abuse(self):
        hello = catalog.get('hello_world')
        failures, rows = [], []
        for name, command, check in ABUSE_SCENARIOS:
            before = self._label_count()
            t0 = time.monotonic()
            r = sandbox.run_command(hello, command)
            wall = time.monotonic() - t0
            leftover = self._label_count() - before
            problems = []
            if wall > ABUSE_WALL_LIMIT_S:
                problems.append(f'took {wall:.1f}s')
            if r.correct:
                problems.append('was accepted as correct')
            if leftover > 0:
                problems.append(f'{leftover} container(s) left behind')
            if check and (msg := check(r)):
                problems.append(msg)
            outcome = ('timed_out' if r.timed_out else r.error or r.error_internal
                       or f'exit {r.exit_code}')
            info = r.output.strip()[:40] if name.endswith('(info)') else ''
            rows.append({'scenario': name, 'wall_s': round(wall, 2), 'outcome': outcome,
                         'contained': not problems, 'problems': problems, 'info': info})
            failures.extend(f'abuse {name}: {p}' for p in problems)
        failures.extend(self._canary(hello, rows))
        return failures, rows

    def _canary(self, hello, rows):
        stop = threading.Event()

        def hammer(command):
            while not stop.is_set():
                sandbox.run_command(hello, command)

        threads = [threading.Thread(target=hammer, args=(cmd,), daemon=True)
                   for cmd in (':(){ :|:& };:', 'while :; do :; done')]
        for t in threads:
            t.start()
        time.sleep(1.0)  # let the abusers get going
        failures, durations = [], []
        try:
            for i in range(CANARY_RUNS):
                t0 = time.monotonic()
                r = sandbox.run_command(hello, hello.example)
                wall = time.monotonic() - t0
                durations.append(wall)
                if not r.correct or wall > CANARY_LIMIT_S:
                    failures.append(f'canary run {i + 1}: correct={r.correct} wall={wall:.2f}s')
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=15)
        rows.append({'scenario': f'canary x{CANARY_RUNS} under fork bomb + cpu spin',
                     'wall_s': round(max(durations, default=0), 2),
                     'outcome': f'{CANARY_RUNS - len(failures)}/{CANARY_RUNS} correct',
                     'contained': not failures, 'problems': failures, 'info': ''})
        return failures

    # ---- output --------------------------------------------------------

    def _print_table(self, reports):
        header = (f'{"slug":38} {"pass":>7} {"seq p50":>7} {"seq p95":>7} {"par":>4} {"par s":>6} '
                  f'{"exp-fail":>8} {"print":>5} {"int":>3}  reason')
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for r in reports:
            ef = 'n/a' if not r.expected_failures else (
                'ACCEPT' if r.accepted_expected_failures else 'ok')
            par = 'ok' if r.parallel and r.parallel.correct else 'FAIL'
            slug = r.slug + (' *' if r.excluded else '') + (' (r)' if r.extra.get('randomized') else '')
            reason = '; '.join(r.cut_reasons()) or r.failure_reason
            self.stdout.write(
                f'{slug:38} {r.pass_count:>3}/{r.total_runs:<3} {r.seq_p50:>7.2f} {r.seq_p95:>7.2f} '
                f'{par:>4} {r.par_duration:>6.2f} {ef:>8} {r.printable:>5} {r.internal_count:>3}  {reason}')
        self.stdout.write('(* = excluded, reported only; (r) = randomized)')

    def handle(self, *args, **opts):
        self.overrides = ({'cpuset_cpus': f'0-{opts["host_cpus"] - 1}'} if opts['host_cpus'] else {})
        try:
            reaped = sandbox.reap_stale()
            before = self._label_count()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f'Docker unavailable: {exc}') from exc

        challenges = catalog.all_main_set()
        if opts['only']:
            wanted = {s.strip() for s in opts['only'].split(',') if s.strip()}
            unknown = wanted - {c.slug for c in challenges}
            if unknown:
                raise CommandError(f'unknown slug(s): {", ".join(sorted(unknown))}')
            challenges = [c for c in challenges if c.slug in wanted]

        self.stderr.write(f'Reaped {reaped} stale container(s). Sweeping {len(challenges)} challenge(s)'
                          f' (host-cpus={opts["host_cpus"] or "unpinned"})...')
        started = time.monotonic()
        try:
            reports = self._sweep(challenges, opts)
            abuse_failures, abuse_rows = ([], []) if opts['skip_abuse'] else self._abuse()
        except sandbox.SandboxUnavailable as exc:
            raise CommandError(f'Sandbox unavailable: {exc}') from exc
        after = self._label_count()
        leaked = max(0, after - before)

        self._print_table(reports)
        gating = [r for r in reports if not r.excluded]
        seq = [x.duration_s for r in gating for x in r.sequential]
        par = [r.par_duration for r in gating if r.parallel]
        self.stdout.write('')
        self.stdout.write(f'Sequential: n={len(seq)} p50={verify.percentile(seq, 50):.2f}s '
                          f'p95={verify.percentile(seq, 95):.2f}s')
        self.stdout.write(f'Parallel (x{opts["parallel"]}): n={len(par)} p50={verify.percentile(par, 50):.2f}s '
                          f'p95={verify.percentile(par, 95):.2f}s')
        self.stdout.write(f'host-cpus: {opts["host_cpus"] or "unpinned"}')
        printable_yes = sum(r.printable == 'yes' for r in reports)
        self.stdout.write(f'Printable (report-only): {printable_yes}/{len(reports)} accept a printed answer')
        cut_candidates = {r.slug: r.cut_reasons() for r in gating if r.cut_reasons()}
        if cut_candidates:
            self.stdout.write('Cut candidates:')
            for slug, reasons in cut_candidates.items():
                self.stdout.write(f'  {slug}: {"; ".join(reasons)}')
        if abuse_rows:
            self.stdout.write('')
            self.stdout.write(f'{"abuse scenario":46} {"wall s":>6} {"contained":>9}  outcome')
            for row in abuse_rows:
                extra = f' [{row["info"]}]' if row['info'] else ''
                self.stdout.write(f'{row["scenario"]:46} {row["wall_s"]:>6.2f} '
                                  f'{"yes" if row["contained"] else "NO":>9}  {row["outcome"]}{extra}')
        self.stdout.write('')
        self.stdout.write(f'Leak check: {before} labelled container(s) before, {after} after')
        self.stdout.write(f'Elapsed: {time.monotonic() - started:.0f}s')

        failures = verify.gate_failures(reports, abuse_failures=abuse_failures, leaked=leaked)

        if opts['json_path']:
            payload = {
                'host_cpus': opts['host_cpus'],
                'challenges': [dict(dataclasses.asdict(r), cut_reasons=r.cut_reasons()) for r in reports],
                'abuse': abuse_rows,
                'sequential_p50': verify.percentile(seq, 50), 'sequential_p95': verify.percentile(seq, 95),
                'parallel_p50': verify.percentile(par, 50), 'parallel_p95': verify.percentile(par, 95),
                'leak_before': before, 'leak_after': after, 'failures': failures,
            }
            with open(opts['json_path'], 'w') as f:
                json.dump(payload, f, indent=2)

        if failures:
            self.stdout.write(self.style.ERROR(f'FAILED ({len(failures)}):'))
            for f in failures:
                self.stdout.write(f'  - {f}')
            raise SystemExit(1)
        abuse = 'skipped' if opts['skip_abuse'] else 'contained'
        self.stdout.write(self.style.SUCCESS(f'OK: all non-excluded challenges pass; abuse {abuse}.'))

"""Simulate N concurrent players through ``game.services`` against the real sandbox.

Exercises the semaphore, the docker connection pool, SQLite writes and the
sandbox together, and reports per-submit wall time. Unpinned by design:
``game.services`` never passes ``host_overrides``.
"""

import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection

from challenges import sandbox
from game import services
from game.models import GameSession

WRONG_COMMAND = 'echo bench-wrong-answer'
ABUSE_COMMAND = 'sleep 60'
# time_up means the run outlasted GAME_DURATION_S: those submits never reach the sandbox,
# so they are kept out of the latency samples and fail the run instead of skewing the numbers.
FAILING_STATUSES = (services.INTERNAL, services.UNAVAILABLE, services.TIME_UP)


def leaked_containers() -> list:
    client = sandbox._get_client()
    return client.containers.list(all=True, filters={'label': sandbox.SANDBOX_LABEL})


def _pct(values: list[float], p: int) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method='inclusive')[p - 1]


class Command(BaseCommand):
    help = 'Measure per-command latency with N concurrent simulated players (through game.services).'

    def add_arguments(self, parser):
        parser.add_argument('--players', type=int, default=15)
        parser.add_argument('--commands', type=int, default=10, help='commands per player')
        parser.add_argument('--mix', choices=['typical', 'with-abuse'], default='typical',
                            help='typical: alternate wrong answers and correct examples; '
                                 f'with-abuse: player 0 sends {ABUSE_COMMAND!r} every time')
        parser.add_argument('--keep', action='store_true', help='keep the bench-* games afterwards')

    def handle(self, *args, players, commands, mix, keep, **options):
        lock = threading.Lock()
        samples: list[tuple[bool, float]] = []  # (is_abuser, seconds)
        statuses: Counter = Counter()
        lock_errors = 0
        game_ids = []

        def play(i: int) -> None:
            nonlocal lock_errors
            abuser = mix == 'with-abuse' and i == 0
            try:
                game = services.start_game(f'bench-{i}')
                with lock:
                    game_ids.append(game.pk)
                for k in range(commands):
                    if abuser:
                        cmd = ABUSE_COMMAND
                    else:
                        ch = services.current_challenge(game)
                        cmd = ch.example if (ch and k % 2) else WRONG_COMMAND
                    t0 = time.monotonic()
                    try:
                        outcome = services.submit_command(game.pk, cmd)
                    except OperationalError as exc:
                        if 'database is locked' not in str(exc):
                            raise
                        with lock:
                            lock_errors += 1
                        continue
                    dt = time.monotonic() - t0
                    game = outcome.game
                    with lock:
                        if outcome.status != services.TIME_UP:
                            samples.append((abuser, dt))
                        statuses[outcome.status] += 1
            finally:
                connection.close()  # each thread has its own DB connection

        self.stdout.write(f'bench_game: {players} players x {commands} commands, mix={mix}, '
                          f'cap={settings.SANDBOX_MAX_CONCURRENT}, '
                          f'queue timeout={settings.SANDBOX_QUEUE_TIMEOUT_S}s')
        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=players) as pool:
                for f in [pool.submit(play, i) for i in range(players)]:
                    f.result()
        finally:
            elapsed = time.monotonic() - started
            if not keep:
                GameSession.objects.filter(pk__in=game_ids).delete()

        self._report('all players', [s for _, s in samples])
        if mix == 'with-abuse':
            self._report('non-abusers', [s for a, s in samples if not a])
            self._report('abuser', [s for a, s in samples if a])
        self.stdout.write('statuses: ' + ', '.join(f'{k}: {v}' for k, v in sorted(statuses.items())))
        self.stdout.write(f'database is locked: {lock_errors}')
        self.stdout.write(f'elapsed: {elapsed:.1f}s')

        leaked = leaked_containers()
        self.stdout.write(f'leaked containers: {len(leaked)}')
        problems = [f'{statuses[s]} {s}' for s in FAILING_STATUSES if statuses[s]]
        if lock_errors:
            problems.append(f'{lock_errors} database-locked errors')
        if leaked:
            problems.append(f'{len(leaked)} leaked containers')
        if problems:
            raise CommandError('bench_game failed: ' + '; '.join(problems))

    def _report(self, label: str, values: list[float]) -> None:
        if not values:
            self.stdout.write(f'{label}: no samples')
            return
        self.stdout.write(f'{label}: n={len(values)} p50={_pct(values, 50):.3f}s '
                          f'p95={_pct(values, 95):.3f}s max={max(values):.3f}s')

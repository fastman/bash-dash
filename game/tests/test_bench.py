from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TransactionTestCase

from challenges import catalog, sandbox
from game import services
from game.management.commands import bench_game
from game.models import GameSession
from game.tests.fakes import result


class BenchGameTests(TransactionTestCase):
    """The command's contract with a fake sandbox; real numbers come from running it (Phase 4)."""

    def setUp(self):
        catalog.clear_cache()
        services._reset_semaphore()
        self.examples = {c.example for c in catalog.main_set()}
        patches = [
            mock.patch.object(sandbox, 'reap_stale_once'),
            mock.patch.object(sandbox, 'run_command', side_effect=self.fake_run),
            mock.patch.object(bench_game, 'leaked_containers', return_value=[]),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.leaked = self.mocks[2]

    def fake_run(self, challenge, command):
        return result(correct=command == challenge.example)

    def bench(self, *args):
        out = StringIO()
        call_command('bench_game', *args, stdout=out)
        return out.getvalue()

    def test_reports_latency_and_statuses_and_cleans_up(self):
        out = self.bench('--players', '1', '--commands', '6')
        for needle in ('p50', 'p95', 'max', 'ran: 6', 'database is locked: 0'):
            self.assertIn(needle, out)
        self.assertFalse(GameSession.objects.filter(nick__startswith='bench_').exists())

    def test_typical_mix_solves_some_and_misses_some(self):
        self.bench('--players', '1', '--commands', '6', '--keep')
        game = GameSession.objects.get(nick__startswith='bench_')
        self.assertEqual(game.attempts, 6)
        self.assertGreater(game.solved, 0)
        self.assertLess(game.solved, 6)

    def test_with_abuse_mix_sends_sleep_from_one_player(self):
        # The in-memory shared-cache test DB raises "table is locked" on concurrent
        # writers (the WAL file DB does not), so run the players one at a time here.
        real_pool = bench_game.ThreadPoolExecutor
        serial = mock.patch.object(bench_game, 'ThreadPoolExecutor',
                                   lambda max_workers: real_pool(max_workers=1))
        with serial:
            self.bench('--players', '2', '--commands', '2', '--mix', 'with-abuse')
        sent = [c.args[1] for c in self.mocks[1].call_args_list]
        self.assertEqual(sent.count('sleep 60'), 2)

    def test_exits_1_on_internal_status(self):
        self.mocks[1].side_effect = lambda ch, cmd: result(error_internal='boom')
        with self.assertRaises(CommandError):
            self.bench('--players', '1', '--commands', '1')

    def test_exits_1_on_leaked_containers(self):
        self.leaked.return_value = ['abc123']
        with self.assertRaises(CommandError):
            self.bench('--players', '1', '--commands', '1')

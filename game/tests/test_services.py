import threading
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from challenges import catalog, sandbox
from challenges.tests.fakes import write_excluded
from game import services
from game.models import Attempt, GameSession
from game.tests.fakes import result


class ServiceTestCase(TestCase):
    def setUp(self):
        catalog.clear_cache()
        self.addCleanup(catalog.clear_cache)
        services._reset_semaphore()
        self.addCleanup(services._reset_semaphore)
        reap = mock.patch.object(sandbox, 'reap_stale_once')
        self.reap = reap.start()
        self.addCleanup(reap.stop)
        run = mock.patch.object(sandbox, 'run_command', return_value=result())
        self.run_command = run.start()
        self.addCleanup(run.stop)
        self.order = [c.slug for c in catalog.main_set()]

    def cut(self, *slugs):
        ctx = override_settings(CHALLENGES_EXCLUDED=write_excluded(''.join(f'{s}: "cut"\n' for s in slugs)))
        ctx.enable()
        self.addCleanup(ctx.disable)
        catalog.clear_cache()

    def fresh(self, game):
        return GameSession.objects.get(pk=game.pk)


class StartGameTests(ServiceTestCase):
    def test_valid_nick_starts_on_first_playable_challenge(self):
        game = services.start_game('  neo  ')
        game = self.fresh(game)
        self.assertEqual(game.nick, 'neo')
        self.assertEqual(game.current_slug, 'hello_world')
        self.assertEqual((game.attempts, game.solved), (0, 0))
        self.assertIsNotNone(game.started_at)
        self.assertFalse(game.is_finished)

    def test_empty_and_too_long_nicks_are_rejected(self):
        for nick in ('', '   ', 'x' * 21):
            with self.assertRaises(ValueError, msg=repr(nick)):
                services.start_game(nick)
        services.start_game('x' * 20)  # boundary is fine
        self.assertEqual(GameSession.objects.count(), 1)


class SubmitCommandTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.game = services.start_game('neo')

    def test_incorrect_command_is_counted_and_stays(self):
        self.run_command.return_value = result(False, output='nope\n', error='Test failed')
        outcome = services.submit_command(self.game.id, 'ls')
        self.assertEqual(outcome.status, 'ran')
        self.assertFalse(outcome.result.correct)
        game = self.fresh(self.game)
        self.assertEqual((game.attempts, game.solved, game.current_slug), (1, 0, 'hello_world'))
        attempt = Attempt.objects.get()
        self.assertEqual((attempt.slug, attempt.command, attempt.output, attempt.error),
                         ('hello_world', 'ls', 'nope\n', 'Test failed'))
        self.assertEqual(attempt.duration_ms, 120)

    def test_correct_command_counts_solves_and_advances(self):
        self.run_command.return_value = result(True, output='hello world\n')
        outcome = services.submit_command(self.game.id, 'echo hello world')
        self.assertEqual(outcome.status, 'ran')
        game = self.fresh(self.game)
        self.assertEqual((game.attempts, game.solved), (1, 1))
        self.assertIsNotNone(game.last_solved_at)
        self.assertEqual(game.current_slug, self.order[1])
        self.assertEqual(outcome.game.current_slug, self.order[1])
        # the command reaches the sandbox verbatim, for the challenge it was on
        ch, cmd = self.run_command.call_args.args
        self.assertEqual((ch.slug, cmd), ('hello_world', 'echo hello world'))

    def test_solving_the_last_challenge_finishes_the_game(self):
        GameSession.objects.filter(pk=self.game.pk).update(current_slug=self.order[-1])
        self.run_command.return_value = result(True)
        services.submit_command(self.game.id, 'x')
        game = self.fresh(self.game)
        self.assertIsNone(game.current_slug)
        self.assertIsNotNone(game.finished_at)
        self.assertTrue(game.is_finished)
        self.assertEqual(game.solved, 1)

    def test_submit_on_finished_game_is_not_counted(self):
        GameSession.objects.filter(pk=self.game.pk).update(current_slug=self.order[-1])
        self.run_command.return_value = result(True)
        services.submit_command(self.game.id, 'x')
        outcome = services.submit_command(self.game.id, 'y')
        self.assertEqual(outcome.status, 'finished')
        self.assertEqual(self.fresh(self.game).attempts, 1)
        self.assertEqual(self.run_command.call_count, 1)

    def test_rejections_are_not_counted_and_never_reach_the_sandbox(self):
        for cmd, status in (('   ', 'empty'), ('', 'empty'), ('x' * 301, 'too_long')):
            self.assertEqual(services.submit_command(self.game.id, cmd).status, status)
        self.run_command.assert_not_called()
        self.assertEqual(self.fresh(self.game).attempts, 0)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_sandbox_unavailable_is_not_counted(self):
        self.run_command.side_effect = sandbox.SandboxUnavailable('daemon down')
        self.assertEqual(services.submit_command(self.game.id, 'ls').status, 'unavailable')
        self.assertEqual(self.fresh(self.game).attempts, 0)

    def test_internal_error_is_not_counted_stored_or_shown_and_is_logged(self):
        self.run_command.return_value = result(error_internal='sandbox exited with status 2')
        with self.assertLogs('game', level='ERROR') as logs:
            outcome = services.submit_command(self.game.id, 'ls -la')
        self.assertEqual(outcome.status, 'internal')
        self.assertIn('hello_world', logs.output[0])
        self.assertIn('ls -la', logs.output[0])
        self.assertEqual(self.fresh(self.game).attempts, 0)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_timed_out_run_is_counted(self):
        self.run_command.return_value = result(timed_out=True, duration_s=5.2)
        outcome = services.submit_command(self.game.id, 'sleep 60')
        self.assertEqual(outcome.status, 'ran')
        self.assertEqual(self.fresh(self.game).attempts, 1)
        self.assertTrue(Attempt.objects.get().timed_out)

    def test_reaps_orphans_before_running(self):
        services.submit_command(self.game.id, 'ls')
        self.reap.assert_called()

    @override_settings(SANDBOX_MAX_CONCURRENT=1, SANDBOX_QUEUE_TIMEOUT_S=0.01)
    def test_busy_when_no_sandbox_slot_frees_up_in_time(self):
        services._reset_semaphore()
        sem = services._get_semaphore()
        self.assertTrue(sem.acquire(timeout=1))
        try:
            outcome = services.submit_command(self.game.id, 'ls')
        finally:
            sem.release()
        self.assertEqual(outcome.status, 'busy')
        self.run_command.assert_not_called()
        self.assertEqual(self.fresh(self.game).attempts, 0)

    @override_settings(SANDBOX_MAX_CONCURRENT=1, SANDBOX_QUEUE_TIMEOUT_S=0.01)
    def test_slot_is_released_when_sandbox_is_unavailable(self):
        services._reset_semaphore()
        self.run_command.side_effect = [sandbox.SandboxUnavailable('down'), result()]
        self.assertEqual(services.submit_command(self.game.id, 'ls').status, 'unavailable')
        self.assertEqual(services.submit_command(self.game.id, 'ls').status, 'ran')

    def test_duplicate_correct_submit_advances_exactly_once(self):
        # The second submit is loaded on the same slug before the first one commits.
        calls = []

        def run(challenge, command):
            calls.append(challenge.slug)
            if len(calls) == 1:
                services.submit_command(self.game.id, command)
            return result(True)

        self.run_command.side_effect = run
        services.submit_command(self.game.id, 'echo hello world')
        self.assertEqual(calls, ['hello_world', 'hello_world'])
        game = self.fresh(self.game)
        self.assertEqual((game.attempts, game.solved, game.current_slug), (2, 1, self.order[1]))

    def test_run_that_overlaps_the_game_finishing_is_neither_stored_nor_counted(self):
        # e.g. a second tab solved the last challenge (or, later, the time limit hit) mid-run.
        def run(challenge, command):
            GameSession.objects.filter(pk=self.game.pk).update(current_slug=None, finished_at=timezone.now())
            return result(False, output='late')

        self.run_command.side_effect = run
        outcome = services.submit_command(self.game.id, 'ls')
        self.assertEqual(outcome.status, 'finished')
        self.assertTrue(outcome.game.is_finished)
        self.assertEqual(Attempt.objects.count(), 0)
        self.assertEqual(self.fresh(self.game).attempts, 0)

    def test_last_attempt_is_the_most_recent_run(self):
        self.assertIsNone(services.last_attempt(self.game))
        self.run_command.side_effect = [result(output='one'), result(output='two')]
        services.submit_command(self.game.id, 'a')
        services.submit_command(self.game.id, 'b')
        self.assertEqual(services.last_attempt(self.game).command, 'b')


class CutMidGameTests(ServiceTestCase):
    def test_cut_current_slug_resolves_to_next_playable_and_persists(self):
        game = services.start_game('neo')
        GameSession.objects.filter(pk=game.pk).update(current_slug=self.order[1])
        self.cut(self.order[1])
        ch = services.current_challenge(self.fresh(game))
        self.assertEqual(ch.slug, self.order[2])
        self.assertEqual(self.fresh(game).current_slug, self.order[2])

    def test_cut_last_slug_finishes_the_game_without_a_solve(self):
        game = services.start_game('neo')
        GameSession.objects.filter(pk=game.pk).update(current_slug=self.order[-1])
        self.cut(self.order[-1])
        self.assertIsNone(services.current_challenge(self.fresh(game)))
        game = self.fresh(game)
        self.assertIsNone(game.current_slug)
        self.assertIsNotNone(game.finished_at)
        self.assertEqual(game.solved, 0)
        self.assertEqual(services.submit_command(game.id, 'ls').status, 'finished')

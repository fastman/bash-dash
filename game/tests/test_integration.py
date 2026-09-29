"""Game service against the real sandbox. Skipped when Docker or the sandbox image is unavailable."""

import unittest

import docker
from django.test import TransactionTestCase

from challenges import catalog, sandbox
from challenges.tests.test_sandbox_integration import AVAILABLE, REASON
from game import services
from game.models import GameSession


@unittest.skipUnless(AVAILABLE, REASON)
class GameIntegrationTests(TransactionTestCase):
    def setUp(self):
        catalog.clear_cache()
        services._reset_semaphore()

    def test_correct_then_wrong_command_against_real_sandbox(self):
        game = services.start_game('itest')
        first = catalog.first_playable()
        outcome = services.submit_command(game.id, first.example)
        self.assertEqual(outcome.status, 'ran', outcome)
        self.assertTrue(outcome.result.correct, outcome.result)
        self.assertEqual(outcome.game.current_slug, catalog.next_playable(first.slug).slug)

        outcome = services.submit_command(game.id, 'echo definitely wrong')
        self.assertEqual(outcome.status, 'ran')
        self.assertFalse(outcome.result.correct)
        game = GameSession.objects.get(pk=game.pk)
        self.assertEqual((game.attempts, game.solved), (2, 1))

        leaked = docker.from_env().containers.list(all=True, filters={'label': sandbox.SANDBOX_LABEL})
        self.assertEqual(leaked, [])

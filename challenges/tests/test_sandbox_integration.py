"""Real-container tests. Skipped when Docker or the sandbox image is unavailable."""

import time
import unittest

from django.conf import settings
from django.test import SimpleTestCase

from challenges import catalog, sandbox


def _sandbox_available() -> tuple[bool, str]:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.images.get(settings.SANDBOX_IMAGE)
    except Exception as exc:  # noqa: BLE001
        return False, f'Docker or image {settings.SANDBOX_IMAGE} unavailable ({exc}); run sandbox/build.sh'
    return True, ''


AVAILABLE, REASON = _sandbox_available()


@unittest.skipUnless(AVAILABLE, REASON)
class SandboxIntegrationTests(SimpleTestCase):
    def test_hello_world_example_is_correct(self):
        ch = catalog.get('hello_world')
        result = sandbox.run_command(ch, ch.example)
        self.assertTrue(result.correct, result)

    def test_expected_failure_of_randomized_challenge_is_rejected(self):
        ch = catalog.get('sum_all_numbers')
        result = sandbox.run_command(ch, ch.expected_failures[0])
        self.assertFalse(result.correct, result)
        self.assertEqual(result.error_internal, '')

    def test_long_running_command_times_out_within_7s(self):
        t0 = time.monotonic()
        result = sandbox.run_command(catalog.get('hello_world'), 'sleep 60')
        self.assertLess(time.monotonic() - t0, 7.0)
        self.assertFalse(result.correct)
        self.assertTrue(result.timed_out)

import base64
import importlib
from unittest import mock

import docker
import docker.errors
from django.test import SimpleTestCase

from challenges import catalog, sandbox
from challenges.tests.fakes import FakeClient, FakeContainer, aged, runcmd_json

MEMORY_ERROR = 'Command used too much memory or output'
TOO_LARGE_ERROR = 'Output too large (limit about 1 MB)'


class RunCommandTests(SimpleTestCase):
    def setUp(self):
        self.ch = catalog.get('hello_world')

    def run_with(self, container, command='echo hello world', **client_kwargs):
        client = FakeClient(container, **client_kwargs)
        return sandbox.run_command(self.ch, command, client=client), client

    def test_parses_runcmd_json_into_result(self):
        c = FakeContainer(logs=b'noise\n' + runcmd_json(Correct=True, Output='hello world\n', ExitCode=0))
        result, _ = self.run_with(c)
        self.assertIsInstance(result, sandbox.SandboxResult)
        self.assertTrue(result.correct)
        self.assertEqual(result.output, 'hello world\n')
        self.assertEqual(result.error, '')
        self.assertEqual(result.error_internal, '')
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.duration_s, 0)
        self.assertEqual(c.removed_with, {'force': True, 'v': True})

    def test_incorrect_answer_carries_error(self):
        c = FakeContainer(logs=runcmd_json(Correct=False, Error='Test failed', ExitCode=1))
        result, _ = self.run_with(c)
        self.assertFalse(result.correct)
        self.assertEqual(result.error, 'Test failed')
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.error_internal, '')

    def test_runcmd_timeout_maps_to_timed_out_without_internal_error(self):
        c = FakeContainer(logs=runcmd_json(ErrorInternal='timed out executing command', ExitCode=-1))
        result, _ = self.run_with(c, command='sleep 60')
        self.assertTrue(result.timed_out)
        self.assertFalse(result.correct)
        self.assertEqual(result.error_internal, '')

    def test_oom_kill_maps_to_memory_error(self):
        c = FakeContainer(logs=b'', exit_code=137, oom_killed=True)
        result, _ = self.run_with(c, command='yes')
        self.assertFalse(result.correct)
        self.assertEqual(result.error, MEMORY_ERROR)
        self.assertEqual(result.error_internal, '')

    def test_exit_137_without_json_maps_to_memory_error(self):
        c = FakeContainer(logs=b'', exit_code=137)
        result, _ = self.run_with(c)
        self.assertEqual(result.error, MEMORY_ERROR)
        self.assertEqual(result.error_internal, '')

    def test_truncated_large_log_maps_to_output_too_large(self):
        c = FakeContainer(logs=b'{"Correct":false,"Output":"' + b'1\\n' * 400_000, exit_code=0)
        result, _ = self.run_with(c)
        self.assertFalse(result.correct)
        self.assertEqual(result.error, TOO_LARGE_ERROR)
        self.assertEqual(result.error_internal, '')

    def test_rotated_log_tail_with_clean_exit_maps_to_output_too_large(self):
        # json-file max-size=1m rotates: the kept tail can be any size below 1 MB.
        c = FakeContainer(logs=b'7110\\n237111\\n237112\\n"}\n', exit_code=0)
        result, _ = self.run_with(c, command='seq 1 300000')
        self.assertEqual(result.error, TOO_LARGE_ERROR)
        self.assertEqual(result.error_internal, '')

    def test_other_unparsable_output_is_internal_error(self):
        c = FakeContainer(logs=b'sandbox-entry: missing fixture dir\n', exit_code=3)
        result, _ = self.run_with(c)
        self.assertFalse(result.correct)
        self.assertEqual(result.error, '')
        self.assertTrue(result.error_internal)

    def test_nonzero_exit_with_json_is_internal_error(self):
        c = FakeContainer(logs=runcmd_json(Correct=True), exit_code=1)
        result, _ = self.run_with(c)
        self.assertFalse(result.correct)
        self.assertTrue(result.error_internal)

    def test_host_wait_timeout_kills_and_reports_timed_out(self):
        c = FakeContainer(logs=b'', wait_timeout=True)
        result, _ = self.run_with(c, command='sleep 60')
        self.assertTrue(c.killed)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.correct)
        self.assertEqual(result.error_internal, '')
        self.assertEqual(c.wait_calls, [sandbox.HOST_TIMEOUT_S])
        self.assertEqual(c.removed_with, {'force': True, 'v': True})

    def test_docker_error_after_start_becomes_result_and_still_removes(self):
        c = FakeContainer(logs_error=docker.errors.APIError('boom'))
        result, _ = self.run_with(c)
        self.assertFalse(result.correct)
        self.assertIn('boom', result.error_internal)
        self.assertEqual(c.removed_with, {'force': True, 'v': True})

    def test_output_is_truncated_to_64kb(self):
        c = FakeContainer(logs=runcmd_json(Correct=False, Output='x' * 100_000))
        result, _ = self.run_with(c)
        self.assertEqual(len(result.output), sandbox.MAX_OUTPUT_CHARS)
        self.assertEqual(sandbox.MAX_OUTPUT_CHARS, 64 * 1024)

    def test_missing_image_raises_sandbox_unavailable(self):
        with self.assertRaises(sandbox.SandboxUnavailable):
            self.run_with(FakeContainer(), image_present=False)

    def test_daemon_error_before_container_raises_sandbox_unavailable(self):
        with self.assertRaises(sandbox.SandboxUnavailable):
            self.run_with(None, run_error=docker.errors.DockerException('daemon down'))

    def test_rejects_commands_over_300_chars(self):
        with self.assertRaises(ValueError):
            sandbox.run_command(self.ch, 'x' * 301, client=FakeClient(FakeContainer()))
        # exactly 300 is fine
        c = FakeContainer(logs=runcmd_json())
        sandbox.run_command(self.ch, 'x' * 300, client=FakeClient(c))

    def test_passes_dir_slug_base64_and_full_profile(self):
        ch = catalog.get('sum_all_numbers')
        cmd = "awk '{s+=$1} END {print s}' *"
        client = FakeClient(FakeContainer(logs=runcmd_json()))
        sandbox.run_command(ch, cmd, client=client)
        call = client.containers.run_calls[0]
        self.assertEqual(call['command'], [ch.dir, ch.slug, base64.b64encode(cmd.encode()).decode()])
        self.assertTrue(call['detach'])
        self.assertNotIn('auto_remove', call)
        for key, value in sandbox.SANDBOX_RUN_PROFILE.items():
            self.assertEqual(call[key], value, key)

    def test_profile_matches_hardening_table(self):
        p = sandbox.SANDBOX_RUN_PROFILE
        self.assertEqual(p['network_mode'], 'none')
        self.assertEqual((p['mem_limit'], p['memswap_limit']), ('100m', '100m'))
        self.assertEqual(p['pids_limit'], 64)
        self.assertEqual(p['nano_cpus'], 500_000_000)
        self.assertEqual(p['cap_drop'], ['ALL'])
        self.assertEqual(p['security_opt'], ['no-new-privileges'])
        self.assertEqual(p['user'], '1000:1000')
        self.assertTrue(p['read_only'])
        self.assertEqual(p['tmpfs'], {
            '/var/challenges': 'size=16m,mode=1777,exec',
            '/tmp': 'size=16m,mode=1777',
        })
        self.assertEqual(p['shm_size'], '1m')
        self.assertEqual(p['environment'], {'GOMAXPROCS': '1'})
        self.assertEqual(p['log_config'], {'type': 'json-file', 'config': {'max-size': '1m'}})
        self.assertEqual(p['labels'], {'bash-dash.sandbox': '1'})


class LazyClientTests(SimpleTestCase):
    def test_import_does_not_create_a_docker_client(self):
        with mock.patch.object(docker, 'from_env', side_effect=AssertionError('created at import')) as fe:
            importlib.reload(sandbox)
            fe.assert_not_called()
        importlib.reload(sandbox)

    def test_client_is_created_lazily_and_cached(self):
        fake = FakeClient(FakeContainer(logs=runcmd_json(Correct=True)))
        with mock.patch.object(docker, 'from_env', return_value=fake) as fe:
            importlib.reload(sandbox)
            ch = catalog.get('hello_world')
            sandbox.run_command(ch, 'echo hi')
            sandbox.run_command(ch, 'echo hi')
            fe.assert_called_once()
        importlib.reload(sandbox)


class ReapStaleTests(SimpleTestCase):
    def test_removes_only_exited_or_old_labelled_containers(self):
        exited = FakeContainer(status='exited', created=aged(5))
        old_running = FakeContainer(status='running', created=aged(120))
        fresh_running = FakeContainer(status='running', created=aged(5))
        client = FakeClient(listed=[exited, old_running, fresh_running])
        removed = sandbox.reap_stale(max_age_s=60, client=client)
        self.assertEqual(removed, 2)
        self.assertEqual(exited.removed_with, {'force': True, 'v': True})
        self.assertEqual(old_running.removed_with, {'force': True, 'v': True})
        self.assertIsNone(fresh_running.removed_with)
        self.assertEqual(client.containers.list_calls,
                         [{'all': True, 'filters': {'label': 'bash-dash.sandbox'}}])

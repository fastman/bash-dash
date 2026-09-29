import base64
import importlib
from unittest import mock

import docker
import docker.errors
from django.test import SimpleTestCase, override_settings

from challenges import catalog, sandbox
from challenges.tests.fakes import FakeClient, FakeContainer, aged, runcmd_json

MEMORY_ERROR = 'Command used too much memory or output'
TOO_LARGE_ERROR = 'Output too large (limit about 1 MB)'
TAMPER_ERROR = 'Command interfered with the sandbox output'


class RunCommandTests(SimpleTestCase):
    def setUp(self):
        self.ch = catalog.get('hello_world')

    def run_with(self, container, command='echo hello world', **client_kwargs):
        client = FakeClient(container, **client_kwargs)
        return sandbox.run_command(self.ch, command, client=client), client

    def test_parses_runcmd_json_into_result(self):
        c = FakeContainer(logs=runcmd_json(Correct=True, Output='hello world\n', ExitCode=0))
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

    def test_extra_stdout_line_is_never_correct(self):
        # A player writing to runcmd's stdout (/proc/1/fd/1) must not forge a verdict,
        # whether the forged line comes before or after runcmd's own JSON.
        forged = runcmd_json(Correct=True, Output='pwn')
        for logs in (runcmd_json(Correct=False) + forged, forged + runcmd_json(Correct=False),
                     b'noise\n' + forged):
            c = FakeContainer(logs=logs)
            result, _ = self.run_with(c)
            self.assertFalse(result.correct, logs)
            self.assertEqual(result.error, TAMPER_ERROR)
            self.assertEqual(result.error_internal, '')
            self.assertEqual(c.removed_with, {'force': True, 'v': True})

    def test_whole_but_invalid_runcmd_line_is_internal_error(self):
        c = FakeContainer(logs=b'{"Correct":true,"Output":"x"\n', exit_code=0)
        result, _ = self.run_with(c)
        self.assertFalse(result.correct)
        self.assertEqual(result.error, '')
        self.assertTrue(result.error_internal)

    def test_entrypoint_failures_are_internal_errors_with_reason(self):
        for status, needle in ((64, 'usage'), (65, 'fixture')):
            c = FakeContainer(logs=b'', exit_code=status)
            result, _ = self.run_with(c)
            self.assertFalse(result.correct)
            self.assertIn(needle, result.error_internal)

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
        c = FakeContainer(logs=b'panic: boom\n', exit_code=2)
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

    def test_failed_start_removes_container_and_raises_unavailable(self):
        c = FakeContainer(start_error=docker.errors.APIError('invalid cpuset'))
        with self.assertRaises(sandbox.SandboxUnavailable):
            self.run_with(c)
        self.assertEqual(c.removed_with, {'force': True, 'v': True})

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
        call = client.containers.create_calls[0]
        self.assertEqual(call['command'], [ch.dir, ch.slug, base64.b64encode(cmd.encode()).decode()])
        self.assertTrue(client.containers.container.started)
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

    def test_client_pool_is_sized_to_concurrency_cap(self):
        fake = FakeClient(FakeContainer(logs=runcmd_json(Correct=True)))
        with override_settings(SANDBOX_MAX_CONCURRENT=5), \
                mock.patch.object(docker, 'from_env', return_value=fake) as fe:
            importlib.reload(sandbox)
            sandbox.run_command(catalog.get('hello_world'), 'echo hi')
            fe.assert_called_once_with(max_pool_size=7)
        importlib.reload(sandbox)


class ImageCheckCacheTests(SimpleTestCase):
    def setUp(self):
        sandbox.clear_image_cache()
        self.addCleanup(sandbox.clear_image_cache)
        self.ch = catalog.get('hello_world')

    def test_image_is_checked_once_per_client(self):
        client = FakeClient(FakeContainer(logs=runcmd_json()))
        sandbox.run_command(self.ch, 'echo a', client=client)
        sandbox.run_command(self.ch, 'echo b', client=client)
        self.assertEqual(len(client.images.requested), 1)

    def test_image_not_found_on_create_invalidates_cache(self):
        client = FakeClient(FakeContainer(logs=runcmd_json()))
        sandbox.run_command(self.ch, 'echo a', client=client)
        client.containers.run_error = docker.errors.ImageNotFound('gone')
        with self.assertRaises(sandbox.SandboxUnavailable):
            sandbox.run_command(self.ch, 'echo b', client=client)
        client.containers.run_error = None
        sandbox.run_command(self.ch, 'echo c', client=client)
        self.assertEqual(len(client.images.requested), 2)


class ReapStaleTests(SimpleTestCase):
    def test_removes_only_exited_or_old_labelled_containers(self):
        exited = FakeContainer(status='exited', created=aged(5))
        never_started = FakeContainer(status='created', created=aged(5))
        old_running = FakeContainer(status='running', created=aged(120))
        fresh_running = FakeContainer(status='running', created=aged(5))
        client = FakeClient(listed=[exited, never_started, old_running, fresh_running])
        removed = sandbox.reap_stale(max_age_s=60, client=client)
        self.assertEqual(removed, 3)
        self.assertEqual(never_started.removed_with, {'force': True, 'v': True})
        self.assertEqual(exited.removed_with, {'force': True, 'v': True})
        self.assertEqual(old_running.removed_with, {'force': True, 'v': True})
        self.assertIsNone(fresh_running.removed_with)
        self.assertEqual(client.containers.list_calls,
                         [{'all': True, 'filters': {'label': 'bash-dash.sandbox'}}])

    def test_min_age_protects_young_containers_whatever_their_status(self):
        young_exited = FakeContainer(status='exited', created=aged(5))
        young_created = FakeContainer(status='created', created=aged(29))
        old_exited = FakeContainer(status='exited', created=aged(31))
        old_running = FakeContainer(status='running', created=aged(120))
        mid_running = FakeContainer(status='running', created=aged(45))
        client = FakeClient(listed=[young_exited, young_created, old_exited, old_running, mid_running])
        removed = sandbox.reap_stale(max_age_s=60, min_age_s=30, client=client)
        self.assertEqual(removed, 2)
        self.assertIsNone(young_exited.removed_with)
        self.assertIsNone(young_created.removed_with)
        self.assertIsNone(mid_running.removed_with)
        self.assertEqual(old_exited.removed_with, {'force': True, 'v': True})
        self.assertEqual(old_running.removed_with, {'force': True, 'v': True})


class ReapStaleOnceTests(SimpleTestCase):
    def setUp(self):
        sandbox._reset_reap_once()
        self.addCleanup(sandbox._reset_reap_once)

    def test_reaps_once_per_process_with_game_min_age(self):
        with mock.patch.object(sandbox, 'reap_stale', return_value=0) as rs:
            sandbox.reap_stale_once()
            sandbox.reap_stale_once()
        rs.assert_called_once_with(min_age_s=sandbox.GAME_REAP_MIN_AGE_S)
        self.assertEqual(sandbox.GAME_REAP_MIN_AGE_S, 30)

    def test_docker_error_is_swallowed_and_retried_next_call(self):
        with mock.patch.object(sandbox, 'reap_stale',
                               side_effect=[docker.errors.DockerException('down'), 0, 0]) as rs:
            with self.assertLogs('challenges.sandbox', level='WARNING'):
                sandbox.reap_stale_once()
            sandbox.reap_stale_once()
            sandbox.reap_stale_once()
        self.assertEqual(rs.call_count, 2)

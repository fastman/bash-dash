from django.test import SimpleTestCase

from challenges import catalog, sandbox, verify
from challenges.tests.fakes import FakeClient, FakeContainer, runcmd_json


def res(correct=True, duration=0.5, error='', error_internal='', timed_out=False):
    return sandbox.SandboxResult(correct=correct, output='', error=error, error_internal=error_internal,
                                 exit_code=0, timed_out=timed_out, duration_s=duration)


class HelperTests(SimpleTestCase):
    def test_percentile_nearest_rank(self):
        values = [0.1 * i for i in range(1, 21)]  # 0.1 .. 2.0
        self.assertAlmostEqual(verify.percentile(values, 50), 1.0)
        self.assertAlmostEqual(verify.percentile(values, 95), 1.9)
        self.assertEqual(verify.percentile([], 95), 0.0)

    def test_randomized_slugs_come_from_go_table_and_cover_9_main_set_challenges(self):
        main = {c.slug for c in catalog.all_main_set()}
        randomized = verify.randomized_slugs() & main
        self.assertEqual(len(randomized), 9)
        self.assertIn('find_primes', randomized)
        self.assertIn('sum_all_numbers', randomized)

    def test_printable_command_prints_expected_lines_or_none_when_too_long(self):
        ch = catalog.get('hello_world')
        self.assertEqual(verify.printable_command(ch), "printf '%s\\n' 'hello world'")
        self.assertIsNone(verify.printable_command(catalog.get('print_sorted_by_key')))


class ChallengeReportTests(SimpleTestCase):
    def report(self, seq, parallel=None, ef=None, excluded=False):
        return verify.ChallengeReport(slug='x', excluded=excluded, sequential=seq,
                                      parallel=parallel or res(), expected_failures=ef or {},
                                      printable='n/a')

    def test_clean_challenge_has_no_cut_reasons(self):
        r = self.report([res(), res(), res()])
        self.assertEqual(r.cut_reasons(), [])
        self.assertEqual(r.pass_count, 4)
        self.assertEqual(r.total_runs, 4)
        self.assertEqual(r.internal_count, 0)

    def test_verifier_no_or_timeout_cuts(self):
        self.assertIn('verifier rejected example: Test failed',
                      self.report([res(), res(correct=False, error='Test failed')]).cut_reasons())
        self.assertIn('timed out',
                      self.report([res()], parallel=res(correct=False, timed_out=True)).cut_reasons())

    def test_error_internal_fails_but_never_cuts(self):
        r = self.report([res(correct=False, error_internal='boom')])
        self.assertEqual(r.cut_reasons(), [])
        self.assertEqual(r.internal_count, 1)
        self.assertEqual(r.failure_reason, 'internal: boom')

    def test_slow_p95_cuts(self):
        reasons = self.report([res(duration=4.5)] * 3).cut_reasons()
        self.assertTrue(any('sequential p95 4.50s' in r for r in reasons), reasons)
        reasons = self.report([res()], parallel=res(duration=4.2)).cut_reasons()
        self.assertTrue(any('parallel p95 4.20s' in r for r in reasons), reasons)

    def test_accepted_expected_failure_cuts(self):
        r = self.report([res()], ef={'echo 0': res(correct=True)})
        self.assertIn("expected failure accepted: 'echo 0'", r.cut_reasons())


class VerdictTests(SimpleTestCase):
    def test_excluded_challenges_never_gate(self):
        bad = verify.ChallengeReport(slug='bad', excluded=True, sequential=[res(correct=False, error='no')],
                                     parallel=res(), expected_failures={}, printable='n/a')
        good = verify.ChallengeReport(slug='good', excluded=False, sequential=[res()], parallel=res(),
                                      expected_failures={}, printable='n/a')
        self.assertEqual(verify.gate_failures([bad, good], abuse_failures=[], leaked=0), [])

    def test_gate_collects_every_failure_kind(self):
        r = verify.ChallengeReport(slug='g', excluded=False,
                                   sequential=[res(correct=False, error_internal='boom'), res(duration=4.5)],
                                   parallel=res(), expected_failures={'echo': res(correct=True)},
                                   printable='n/a')
        failures = verify.gate_failures([r], abuse_failures=['fork bomb: took 9.0s'], leaked=2)
        text = '\n'.join(failures)
        for needle in ('g: not every run was correct', 'g: 1 error_internal', 'g: expected failure accepted',
                       'sequential p95', 'fork bomb', '2 sandbox container(s) leaked'):
            self.assertIn(needle, text)


class SlowChallengeGateTests(SimpleTestCase):
    def test_one_slow_non_excluded_challenge_fails_gate_even_if_overall_p95_ok(self):
        fast = [verify.ChallengeReport(slug=f'f{i}', excluded=False, sequential=[res()] * 3, parallel=res(),
                                       expected_failures={}, printable='n/a') for i in range(30)]
        slow = verify.ChallengeReport(slug='slow', excluded=False, sequential=[res(duration=4.4)] * 3,
                                      parallel=res(), expected_failures={}, printable='n/a')
        failures = verify.gate_failures(fast + [slow], abuse_failures=[], leaked=0)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn('slow: cut candidate: sequential p95 4.40s', failures[0])


class HostOverridesTests(SimpleTestCase):
    def test_host_overrides_are_added_without_touching_profile(self):
        client = FakeClient(FakeContainer(logs=runcmd_json(Correct=True)))
        before = dict(sandbox.SANDBOX_RUN_PROFILE)
        sandbox.run_command(catalog.get('hello_world'), 'echo', client=client,
                            host_overrides={'cpuset_cpus': '0-1'})
        self.assertEqual(client.containers.run_calls[0]['cpuset_cpus'], '0-1')
        self.assertEqual(sandbox.SANDBOX_RUN_PROFILE, before)

    def test_host_overrides_cannot_weaken_profile(self):
        client = FakeClient(FakeContainer(logs=runcmd_json(Correct=True)))
        with self.assertRaises(ValueError):
            sandbox.run_command(catalog.get('hello_world'), 'echo', client=client,
                                host_overrides={'network_mode': 'bridge'})

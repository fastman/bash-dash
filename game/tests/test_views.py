import json
import re
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from challenges import catalog, sandbox
from game import services
from game.models import GameSession
from game.templatetags.game_text import render_description
from game.tests.test_services import result

EXTERNAL_LINK = re.compile(r'<a\s[^>]*href\s*=\s*["\']?(https?:)?//', re.I)


class ViewTestCase(TestCase):
    def setUp(self):
        catalog.clear_cache()
        services._reset_semaphore()
        for target in ('reap_stale_once', 'run_command'):
            patcher = mock.patch.object(sandbox, target)
            setattr(self, target, patcher.start())
            self.addCleanup(patcher.stop)
        self.run_command.return_value = result()
        self.order = catalog.main_set()

    def start(self, nick='neo'):
        return self.client.post(reverse('game:start'), {'nick': nick})

    def game(self):
        return GameSession.objects.get(pk=self.client.session['game_id'])

    def command(self, cmd, client=None, **extra):
        return (client or self.client).post(reverse('game:command'), json.dumps({'command': cmd}),
                                            content_type='application/json', **extra)


class HomeAndStartTests(ViewTestCase):
    def test_home_renders_rules_and_nick_form(self):
        resp = self.client.get(reverse('game:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="nick"')
        self.assertContains(resp, 'maxlength="20"')
        self.assertContains(resp, 'Start')
        self.assertContains(resp, 'attempt')
        self.assertContains(resp, '5 minutes')

    def test_start_with_valid_nick_sets_session_and_redirects_to_play(self):
        resp = self.start('neo')
        self.assertRedirects(resp, reverse('game:play'))
        self.assertEqual(self.game().nick, 'neo')

    def test_start_with_invalid_nick_shows_error_and_creates_no_game(self):
        resp = self.start('   ')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="error"')
        self.assertEqual(GameSession.objects.count(), 0)
        self.assertNotIn('game_id', self.client.session)

    def test_home_and_start_with_active_game_redirect_to_play(self):
        self.start('neo')
        self.assertRedirects(self.client.get(reverse('game:home')), reverse('game:play'))
        self.assertRedirects(self.start('again'), reverse('game:play'))
        self.assertEqual(GameSession.objects.count(), 1)


class PlayTests(ViewTestCase):
    def test_play_without_game_redirects_home(self):
        self.assertRedirects(self.client.get(reverse('game:play')), reverse('game:home'))
        self.assertRedirects(self.client.get(reverse('game:done')), reverse('game:home'))

    def test_play_shows_first_challenge_of_total(self):
        self.start()
        resp = self.client.get(reverse('game:play'))
        self.assertContains(resp, f'1 / {len(self.order)}')
        self.assertContains(resp, self.order[0].title)
        self.assertContains(resp, 'autocapitalize="off"')
        self.assertContains(resp, 'maxlength="300"')

    def test_play_after_reload_shows_last_attempt_escaped(self):
        self.start()
        self.run_command.return_value = result(output='<b>bold</b>\n', error='Test failed')
        self.command('echo "<b>bold</b>"')
        resp = self.client.get(reverse('game:play'))
        self.assertContains(resp, '&lt;b&gt;bold&lt;/b&gt;')
        self.assertNotContains(resp, '<b>bold</b>')
        self.assertContains(resp, 'Test failed')
        self.assertContains(resp, 'data-attempts="1"')

    def test_finishing_redirects_play_to_done(self):
        self.start()
        GameSession.objects.filter(pk=self.game().pk).update(current_slug=self.order[-1].slug)
        self.run_command.return_value = result(True)
        data = self.command('x').json()
        self.assertTrue(data['finished'])
        self.assertIsNone(data['challenge'])
        self.assertRedirects(self.client.get(reverse('game:play')), reverse('game:done'))
        self.assertRedirects(self.client.get(reverse('game:home')), reverse('game:done'))
        resp = self.client.get(reverse('game:done'))
        self.assertContains(resp, 'neo')
        self.assertContains(resp, f'1 / {len(self.order)}')


class CommandJsonTests(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.start()

    def test_incorrect_run_returns_200_with_result_and_counters(self):
        self.run_command.return_value = result(output='file\n', error='Test failed')
        resp = self.command('ls')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ran')
        self.assertEqual((data['attempts'], data['solved'], data['finished']), (1, 0, False))
        self.assertEqual(data['result'], {'correct': False, 'output': 'file\n', 'message': 'Test failed'})
        self.assertEqual(data['challenge']['index'], 1)
        self.assertEqual(data['challenge']['total'], len(self.order))

    def test_correct_run_returns_next_challenge(self):
        self.run_command.return_value = result(True, output='hello world\n')
        data = self.command('echo hello world').json()
        self.assertEqual(data['result']['message'], 'Correct!')
        self.assertEqual(data['challenge']['index'], 2)
        self.assertEqual(data['challenge']['title'], self.order[1].title)
        self.assertIn('description_html', data['challenge'])

    def test_timed_out_run_message(self):
        self.run_command.return_value = result(timed_out=True)
        data = self.command('sleep 60').json()
        self.assertEqual(data['result']['message'], 'Timed out (5 s limit)')
        self.assertEqual(data['attempts'], 1)

    def assert_uncounted(self, resp, code, status):
        self.assertEqual(resp.status_code, code, status)
        data = resp.json()
        self.assertEqual(data['status'], status)
        self.assertEqual(data['attempts'], 0)
        self.assertNotIn('result', data)
        self.assertTrue(data['message'])
        self.assertIn('challenge', data)

    def test_rejected_commands_return_400(self):
        self.assert_uncounted(self.command('   '), 400, 'empty')
        self.assert_uncounted(self.command('x' * 301), 400, 'too_long')

    def test_sandbox_unavailable_returns_503(self):
        self.run_command.side_effect = sandbox.SandboxUnavailable('down')
        with self.assertLogs('game', level='WARNING'):
            self.assert_uncounted(self.command('ls'), 503, 'unavailable')

    def test_internal_error_returns_500_without_leaking_detail(self):
        self.run_command.return_value = result(error_internal='boom secret detail')
        with self.assertLogs('game', level='ERROR'):
            resp = self.command('ls')
        self.assert_uncounted(resp, 500, 'internal')
        self.assertNotIn('secret', resp.content.decode())

    def test_busy_returns_503(self):
        with mock.patch.object(services, 'submit_command',
                               return_value=services.SubmitOutcome('busy', None, self.game())):
            resp = self.command('ls')
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['status'], 'busy')

    def test_finished_game_returns_409(self):
        GameSession.objects.filter(pk=self.game().pk).update(current_slug=self.order[-1].slug)
        self.run_command.return_value = result(True)
        self.command('x')
        resp = self.command('y')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()['status'], 'finished')

    def test_no_game_returns_403(self):
        resp = self.command('ls', client=Client())
        self.assertEqual(resp.status_code, 403)

    def test_invalid_json_body_is_400(self):
        resp = self.client.post(reverse('game:command'), 'not json', content_type='application/json')
        self.assertEqual(resp.status_code, 400)


class CsrfTests(ViewTestCase):
    def test_command_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        game = services.start_game('neo')
        session = client.session
        session['game_id'] = str(game.pk)
        session.save()
        self.assertEqual(client.get(reverse('game:play')).status_code, 200)
        self.assertEqual(self.command('ls', client=client).status_code, 403)
        token = client.cookies['csrftoken'].value
        self.assertEqual(self.command('ls', client=client, HTTP_X_CSRFTOKEN=token).status_code, 200)


class NoAnswerLinksTests(ViewTestCase):
    def test_pages_contain_no_external_links(self):
        pages = [self.client.get(reverse('game:home')).content]
        self.start()
        pages.append(self.client.get(reverse('game:play')).content)
        GameSession.objects.filter(pk=self.game().pk).update(current_slug=self.order[-1].slug)
        self.run_command.return_value = result(True)
        self.command('x')
        pages.append(self.client.get(reverse('game:done')).content)
        for html in pages:
            self.assertIsNone(EXTERNAL_LINK.search(html.decode()), html[:200])


class DescriptionFilterTests(TestCase):
    def test_html_is_escaped(self):
        out = render_description('Run <script>alert(1)</script> & stop')
        self.assertNotIn('<script>', out)
        self.assertIn('&lt;script&gt;', out)
        self.assertIn('&amp;', out)

    def test_backticks_become_code_and_newlines_br(self):
        out = render_description('Use `ls -l` here.\nThen `pwd`.')
        self.assertEqual(out, 'Use <code>ls -l</code> here.<br>Then <code>pwd</code>.')

    def test_fenced_blocks_become_pre_without_inner_markup(self):
        out = render_description('Example:\n```\na `b` <c>\nline2\n```\nDone')
        self.assertEqual(out, 'Example:<pre>a `b` &lt;c&gt;\nline2</pre>Done')

    def test_every_catalog_description_renders(self):
        for ch in catalog.all_main_set():
            self.assertNotIn('```', render_description(ch.description), ch.slug)

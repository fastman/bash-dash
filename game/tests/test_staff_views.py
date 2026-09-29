from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from challenges import catalog
from game import services
from game.models import GameSession

CODE = '987654'


class StaffTestCase(TestCase):
    def setUp(self):
        catalog.clear_cache()
        self.staff = User.objects.create_user('booth', password='x', is_staff=True)
        self.client.force_login(self.staff)
        self.lookup = reverse('game:staff_lookup')
        self.prize = reverse('game:staff_prize')

    def make_game(self, finished=True, solved=1, attempts=3, nick='neo'):
        game = services.start_game(nick)
        fields = dict(code=CODE, solved=solved, attempts=attempts)
        if finished:
            now = game.started_at + timedelta(seconds=75)
            fields.update(finished_at=now, last_solved_at=now if solved else None)
        GameSession.objects.filter(pk=game.pk).update(**fields)
        return GameSession.objects.get(pk=game.pk)


class AccessTests(StaffTestCase):
    def test_anonymous_and_non_staff_are_redirected_to_login(self):
        self.make_game()
        User.objects.create_user('player', password='x')
        for setup in (lambda c: c.logout(), lambda c: c.login(username='player', password='x')):
            client = Client()
            setup(client)
            for resp in (client.get(self.lookup, {'code': CODE}), client.post(self.prize, {'code': CODE})):
                self.assertEqual(resp.status_code, 302)
                self.assertIn('/admin/login/', resp['Location'])
        self.assertIsNone(GameSession.objects.get(code=CODE).prize_given_at)

    def test_post_without_csrf_token_is_forbidden(self):
        self.make_game()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(self.prize, {'code': CODE}).status_code, 403)


class LookupTests(StaffTestCase):
    def test_no_code_shows_form_only(self):
        resp = self.client.get(self.lookup)
        self.assertContains(resp, 'name="code"')
        self.assertContains(resp, 'inputmode="numeric"')
        self.assertNotContains(resp, 'staff-card')

    def test_malformed_and_unknown_codes(self):
        self.assertContains(self.client.get(self.lookup, {'code': '12'}), 'Enter a 6-digit code')
        self.assertContains(self.client.get(self.lookup, {'code': '111111'}), 'No game with code')

    def test_code_with_spaces_finds_game(self):
        self.make_game()
        self.assertContains(self.client.get(self.lookup, {'code': '987 654'}), 'neo')

    def test_finished_game_shows_result_and_button(self):
        self.make_game()
        resp = self.client.get(self.lookup, {'code': CODE})
        for text in ('neo', 'Solved', 'Attempts', '#1 of 1', '1:15', 'Mark prize given'):
            self.assertContains(resp, text)

    def test_unfinished_game_shows_in_progress_and_no_button(self):
        self.make_game(finished=False)
        resp = self.client.get(self.lookup, {'code': CODE})
        self.assertContains(resp, 'Game in progress')
        self.assertNotContains(resp, 'Mark prize given')

    def test_unranked_finished_game_keeps_button(self):
        self.make_game()
        with mock.patch.object(services, 'rank_of', return_value=None):
            resp = self.client.get(self.lookup, {'code': CODE})
        self.assertContains(resp, 'not ranked')
        self.assertContains(resp, 'Mark prize given')


class PrizeTests(StaffTestCase):
    def test_post_marks_once_and_redirects(self):
        self.make_game()
        resp = self.client.post(self.prize, {'code': CODE})
        self.assertRedirects(resp, f'{self.lookup}?code={CODE}')
        stamp = GameSession.objects.get(code=CODE).prize_given_at
        self.assertIsNotNone(stamp)
        page = self.client.get(f'{self.lookup}?code={CODE}')
        self.assertContains(page, 'already given')
        self.assertNotContains(page, 'Mark prize given')

        again = self.client.post(self.prize, {'code': CODE}, follow=True)
        self.assertContains(again, 'already given')
        self.assertEqual(GameSession.objects.get(code=CODE).prize_given_at, stamp)

    def test_post_for_unfinished_game_is_refused(self):
        self.make_game(finished=False)
        resp = self.client.post(self.prize, {'code': CODE}, follow=True)
        self.assertContains(resp, 'still in progress')
        self.assertIsNone(GameSession.objects.get(code=CODE).prize_given_at)

    def test_post_with_unknown_code_shows_error(self):
        resp = self.client.post(self.prize, {'code': '111111'}, follow=True)
        self.assertContains(resp, 'No game with code')


class MmssTests(TestCase):
    def test_rounds_down_and_handles_none(self):
        from game.templatetags.game_text import mmss
        self.assertEqual(mmss(timedelta(seconds=74, milliseconds=900)), '1:14')
        self.assertEqual(mmss(None), '—')

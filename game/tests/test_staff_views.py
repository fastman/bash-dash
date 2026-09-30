from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
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

    def make_game(self, finished=True, solved=1, attempts=3, nick='neo', code=CODE, elapsed=75, finished_ago=0):
        game = services.start_game(nick)
        fields = dict(code=code, solved=solved, attempts=attempts)
        if finished:
            now = game.started_at + timedelta(seconds=elapsed)
            fields['finished_at'] = now - timedelta(seconds=finished_ago)
            fields['last_solved_at'] = now if solved else None
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
            self.assertIn('next=/staff', client.get(self.lookup, {'code': CODE})['Location'])
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
        self.assertNotContains(resp, 'not ranked')

    def test_finished_game_with_no_solves_shows_dash(self):
        self.make_game(solved=0)
        resp = self.client.get(self.lookup, {'code': CODE})
        self.assertContains(resp, 'Solve time: <strong>—</strong>')

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
        self.assertRedirects(resp, f'{self.lookup}?code={CODE}', fetch_redirect_response=False)
        stamp = GameSession.objects.get(code=CODE).prize_given_at
        self.assertIsNotNone(stamp)
        page = self.client.get(f'{self.lookup}?code={CODE}')
        self.assertContains(page, 'Prize given to neo')
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


class HiddenLookupTests(StaffTestCase):
    def test_hidden_game_shows_disqualified_and_keeps_prize_button(self):
        game = self.make_game()
        services.hide_game(game.pk)
        resp = self.client.get(self.lookup, {'code': CODE})
        self.assertContains(resp, 'Hidden from Hall of fame (disqualified)')
        self.assertContains(resp, 'Mark prize given')
        self.assertNotContains(resp, 'not ranked')


class HallTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.hall = reverse('game:staff_hall')
        self.board = reverse('game:staff_hall_board')

    def fixture(self):
        self.make_game(nick='ann', solved=3, attempts=5, code='111111', finished_ago=30)
        self.make_game(nick='bob', solved=2, attempts=4, code='222222', finished_ago=20)
        self.make_game(nick='cy', solved=2, attempts=4, code='333333', finished_ago=10)
        self.make_game(nick='dee', solved=1, attempts=1, code='444444', finished_ago=0)
        return ['111111', '222222', '333333', '444444']

    def test_anonymous_redirects_and_fragment_is_403(self):
        client = Client()
        resp = client.get(self.hall)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])
        self.assertEqual(client.get(self.board).status_code, 403)
        User.objects.create_user('player', password='x')
        client.login(username='player', password='x')
        self.assertEqual(client.get(self.board).status_code, 403)

    def test_rows_in_rank_order_with_shared_places(self):
        self.fixture()
        html = self.client.get(self.board).content.decode()
        self.assertLess(html.index('ann'), html.index('bob'))
        self.assertLess(html.index('bob'), html.index('dee'))
        for text in ('Hall of fame', 'Just finished', '3 / ', '#1', '#2', '#4'):
            self.assertIn(text, html)
        self.assertNotIn('#3', html)

    def test_no_codes_and_hidden_nick_absent_on_page_and_fragment(self):
        codes = self.fixture()
        services.hide_game(GameSession.objects.get(nick='cy').pk)
        for url in (self.hall, self.board):
            html = self.client.get(url).content.decode()
            for code in codes:
                self.assertNotIn(code, html)
            self.assertNotIn('>cy<', html)
            self.assertIn('>ann<', html)

    def test_nick_is_escaped(self):
        self.make_game(nick='<b>x</b>')
        html = self.client.get(self.board).content.decode()
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', html)
        self.assertNotIn('<b>x</b>', html)

    def test_empty_states(self):
        html = self.client.get(self.hall).content.decode()
        self.assertIn('No finished games yet', html)
        self.assertIn('Nobody has finished yet', html)

    def test_fragment_is_not_cached_and_has_no_page_chrome(self):
        resp = self.client.get(self.board)
        self.assertIn('no-store', resp['Cache-Control'])
        self.assertNotContains(resp, '<html')

    @override_settings(HALL_REFRESH_S=7)
    def test_page_carries_polling_config(self):
        html = self.client.get(self.hall).content.decode()
        self.assertIn(f'data-board-url="{self.board}"', html)
        self.assertIn('data-refresh-ms="7000"', html)

    @override_settings(HALL_TOP_N=2, HALL_RECENT_N=1)
    def test_top_n_and_recent_n_truncate(self):
        self.fixture()
        html = self.client.get(self.board).content.decode()
        for nick, shown in (('ann', True), ('bob', True), ('cy', False), ('dee', True)):
            self.assertEqual(f'>{nick}<' in html, shown, nick)

from django.test import SimpleTestCase, override_settings

from challenges import catalog
from challenges.tests.fakes import write_excluded


class CatalogTests(SimpleTestCase):
    def setUp(self):
        catalog.clear_cache()
        self.addCleanup(catalog.clear_cache)

    def test_all_main_set_is_42_untagged_challenges_in_file_order(self):
        challenges = catalog.all_main_set()
        self.assertEqual(len(challenges), 42)
        self.assertEqual(challenges[0].slug, 'hello_world')
        self.assertEqual(challenges[-1].slug, 'IPv4_listening_ports')
        self.assertTrue(all(not c.slug.startswith(('12days', 'oops')) for c in challenges))

    def test_challenge_record_fields(self):
        ch = catalog.get('sum_all_numbers')
        self.assertEqual(ch.slug, 'sum_all_numbers')
        self.assertEqual(ch.dir, 'sum_all_numbers')
        self.assertTrue(ch.title)
        self.assertTrue(ch.description)
        self.assertTrue(ch.example)
        self.assertIsInstance(ch.expected_failures, tuple)
        self.assertGreater(len(ch.expected_failures), 0)
        with self.assertRaises(Exception):
            ch.slug = 'other'  # immutable

    def test_exclusions_are_removed_from_main_set_only(self):
        path = write_excluded('find_primes: "too slow"\n')
        with override_settings(CHALLENGES_EXCLUDED=path):
            catalog.clear_cache()
            slugs = [c.slug for c in catalog.main_set()]
            self.assertEqual(len(slugs), 41)
            self.assertNotIn('find_primes', slugs)
            self.assertEqual(len(catalog.all_main_set()), 42)
            self.assertEqual(catalog.excluded(), {'find_primes': 'too slow'})

    def test_unknown_excluded_slug_raises(self):
        path = write_excluded('no_such_challenge: "typo"\n')
        with override_settings(CHALLENGES_EXCLUDED=path):
            catalog.clear_cache()
            with self.assertRaises(catalog.CatalogError):
                catalog.main_set()

    def test_get_unknown_slug_raises_key_error(self):
        with self.assertRaises(KeyError):
            catalog.get('nope')


class PlayableLookupTests(SimpleTestCase):
    def setUp(self):
        catalog.clear_cache()
        self.addCleanup(catalog.clear_cache)

    def _with_cut(self, text):
        ctx = override_settings(CHALLENGES_EXCLUDED=write_excluded(text))
        ctx.enable()
        self.addCleanup(ctx.disable)
        catalog.clear_cache()

    def test_playable_never_returns_an_excluded_slug(self):
        self._with_cut('current_working_directory: "cut"\n')
        self.assertIsNone(catalog.playable('current_working_directory'))
        self.assertEqual(catalog.playable('hello_world').slug, 'hello_world')
        self.assertIsNone(catalog.playable('no_such_slug'))

    def test_first_playable_skips_excluded_head(self):
        self.assertEqual(catalog.first_playable().slug, 'hello_world')
        self._with_cut('hello_world: "cut"\n')
        self.assertEqual(catalog.first_playable().slug, 'current_working_directory')

    def test_next_playable_skips_excluded_and_works_from_a_cut_slug(self):
        order = [c.slug for c in catalog.all_main_set()]
        self._with_cut(f'{order[1]}: "cut"\n{order[2]}: "cut"\n')
        self.assertEqual(catalog.next_playable(order[0]).slug, order[3])
        self.assertEqual(catalog.next_playable(order[1]).slug, order[3])

    def test_next_playable_returns_none_at_end(self):
        order = [c.slug for c in catalog.all_main_set()]
        self.assertIsNone(catalog.next_playable(order[-1]))
        self._with_cut(f'{order[-1]}: "cut"\n')
        self.assertIsNone(catalog.next_playable(order[-2]))

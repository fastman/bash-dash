"""Settings that depend on the environment (reverse proxy trust)."""

import importlib
import os
from unittest import mock

from django.test import SimpleTestCase

from config import settings as settings_module

ENV_VAR = 'BASHDASH_USE_X_FORWARDED_HOST'
TRACKING_ENV_VAR = 'BASHDASH_TRACKING_WEBSITE_ID'


class ForwardedHostTests(SimpleTestCase):
    """The env var has to reach both settings a deployment behind a proxy relies on."""

    def tearDown(self):
        importlib.reload(settings_module)

    def load(self, **env):
        """Re-run config/settings.py over a patched environ and return the reloaded module."""
        environ = {k: v for k, v in os.environ.items() if k != ENV_VAR}
        environ.update(env)
        with mock.patch.dict(os.environ, environ, clear=True):
            return importlib.reload(settings_module)

    def test_off_by_default(self):
        loaded = self.load()
        self.assertFalse(loaded.USE_X_FORWARDED_HOST)
        self.assertIsNone(loaded.SECURE_PROXY_SSL_HEADER)

    def test_truthy_values_enable_the_proxy_trust(self):
        for value in ('1', 'true', 'True', 'yes'):
            loaded = self.load(**{ENV_VAR: value})
            self.assertTrue(loaded.USE_X_FORWARDED_HOST, value)
            self.assertEqual(loaded.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'), value)

    def test_other_values_leave_it_off(self):
        for value in ('0', 'false', '', 'maybe'):
            loaded = self.load(**{ENV_VAR: value})
            self.assertFalse(loaded.USE_X_FORWARDED_HOST, value)
            self.assertIsNone(loaded.SECURE_PROXY_SSL_HEADER, value)


class TrackingSettingsTests(SimpleTestCase):
    def tearDown(self):
        importlib.reload(settings_module)

    def load(self, value=None):
        environ = {k: v for k, v in os.environ.items() if k != TRACKING_ENV_VAR}
        if value is not None:
            environ[TRACKING_ENV_VAR] = value
        with mock.patch.dict(os.environ, environ, clear=True):
            return importlib.reload(settings_module)

    def test_empty_by_default(self):
        self.assertEqual(self.load().TRACKING_WEBSITE_ID, '')

    def test_reads_website_id_from_environment(self):
        self.assertEqual(self.load('site-id').TRACKING_WEBSITE_ID, 'site-id')

"""The imports a production container must be able to make.

A deploy once took `worker` and `beat` down while the image already running kept
working, and nothing in the diff explained it: the fresh build had resolved a
kombu whose Redis transport imports `packaging` directly, nothing in our
requirements ever asked for it, and it had only ever arrived transitively.

No test touched that import, so the suite stayed green while the containers
crash-looped and the pipeline stopped. These tests import what the worker
imports before it can consume a single task, so the same rebuild fails here
rather than in production.
"""
import importlib

from django.conf import settings
from django.test import SimpleTestCase


class BrokerImportTests(SimpleTestCase):
    """The broker stack, imported the way the worker imports it."""

    def test_broker_is_redis(self):
        # The transport asserted below is only the right one while this holds.
        self.assertTrue(settings.CELERY_BROKER_URL.startswith("redis://"))

    def test_redis_transport_imports(self):
        """kombu resolves this transport while starting the worker."""
        module = importlib.import_module("kombu.transport.redis")
        self.assertTrue(hasattr(module, "Transport"))

    def test_transport_dependencies_are_installed(self):
        """`packaging` is imported by kombu's transport, not by our code.

        A dependency reached only through someone else's import is still a
        dependency of ours, and a rebuild that drops it is an outage.
        """
        self.assertTrue(importlib.import_module("packaging.version"))

    def test_celery_app_builds(self):
        """`celery -A config` is the command both worker and beat run."""
        module = importlib.import_module("config.celery")

        self.assertEqual(module.app.main, "bagwork_rh")

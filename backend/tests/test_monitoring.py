"""Monitoring tests (Spec 05 Phase 8): heartbeat, health payload, checks."""
from django.core.checks import run_checks
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.monitoring.models import Heartbeat
from apps.monitoring.tasks import heartbeat
from config.sentry import init_sentry


class HeartbeatTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_heartbeat_task_writes_single_row(self):
        result = heartbeat()
        self.assertEqual(Heartbeat.objects.count(), 1)
        self.assertIn("heartbeat", result)

        # Calling again must refresh the same row, never create a second.
        heartbeat()
        self.assertEqual(Heartbeat.objects.count(), 1)

    def test_health_reports_dependency_states(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
        self.assertEqual(resp.data["database"], "ok")
        self.assertIn("checks", resp.data)
        self.assertIn("database", resp.data["checks"])
        self.assertIn("redis", resp.data["checks"])
        self.assertIn("heartbeat", resp.data["checks"])


class ProductionChecksTests(TestCase):
    def test_insecure_production_config_fails_check(self):
        with override_settings(
            DEBUG=False,
            SECRET_KEY="unsafe-default-key-change-me",
            ALLOWED_HOSTS=["*"],
            SENTRY_DSN="",
        ):
            errors = run_checks(include_deployment_checks=True)
        ids = {e.id for e in errors}
        self.assertIn("hardening.E001", ids)
        self.assertIn("hardening.E002", ids)
        self.assertIn("hardening.W001", ids)

    def test_secure_config_passes_hardening_checks(self):
        with override_settings(
            DEBUG=False,
            SECRET_KEY="a" * 64,
            ALLOWED_HOSTS=["api.example.com"],
            SENTRY_DSN="https://fake@ingest.example.com/1",
        ):
            errors = run_checks(include_deployment_checks=True)
        ids = {e.id for e in errors}
        self.assertNotIn("hardening.E001", ids)
        self.assertNotIn("hardening.E002", ids)
        self.assertNotIn("hardening.W001", ids)

    def test_checks_are_deployment_only(self):
        """Without `--deploy` the hardening checks must stay silent.

        The test runner calls `manage.py check` (no `--deploy`) with
        `DEBUG=False`; raising here would abort every run.
        """
        with override_settings(
            DEBUG=False,
            SECRET_KEY="unsafe-default-key-change-me",
            ALLOWED_HOSTS=["*"],
            SENTRY_DSN="",
        ):
            errors = run_checks()
        ids = {e.id for e in errors}
        self.assertNotIn("hardening.E001", ids)
        self.assertNotIn("hardening.E002", ids)
        self.assertNotIn("hardening.W001", ids)

    def test_debug_mode_skips_hardening_checks(self):
        with override_settings(DEBUG=True):
            errors = run_checks(include_deployment_checks=True)
        ids = {e.id for e in errors}
        self.assertNotIn("hardening.E001", ids)
        self.assertNotIn("hardening.E002", ids)


class SentryBootstrapTests(TestCase):
    def test_init_is_noop_without_dsn(self):
        self.assertIsNone(init_sentry())
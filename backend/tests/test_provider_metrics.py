"""Provider call instrumentation (Spec 05 Phase 8)."""
import logging

from django.test import TestCase, override_settings

from apps.social.providers import get_provider, instrument_provider
from apps.social.providers.base import SocialProviderError
from apps.social.providers.official import OfficialXProvider


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _FakeProvider:
    platform = "x"

    def get_post(self, token, post_id):
        return {"id": post_id}

    def discover_posts(self, *args, **kwargs):
        raise SocialProviderError("boom")

    def authorize(self, request, scopes, *, state=None, code_verifier=None):
        return "https://example.test/authorize"


class InstrumentProviderTests(TestCase):
    def _capture(self):
        handler = _CaptureHandler()
        logger = logging.getLogger("apps.social.providers")
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        return handler

    def test_success_emits_an_ok_metric(self):
        provider = instrument_provider(_FakeProvider())
        handler = self._capture()

        provider.get_post("tok", "1")

        metric = handler.records[-1].structured
        self.assertEqual(metric["provider"], "x")
        self.assertEqual(metric["operation"], "get_post")
        self.assertEqual(metric["outcome"], "ok")
        self.assertIsInstance(metric["latency_ms"], float)

    def test_error_emits_an_error_metric_and_reraises(self):
        provider = instrument_provider(_FakeProvider())
        handler = self._capture()

        with self.assertRaises(SocialProviderError):
            provider.discover_posts("tok")

        self.assertEqual(handler.records[-1].structured["outcome"], "error")
        self.assertEqual(handler.records[-1].structured["operation"], "discover_posts")

    def test_authorize_is_not_metered(self):
        # authorize only builds a local URL; timing it measures nothing.
        provider = instrument_provider(_FakeProvider())
        handler = self._capture()

        provider.authorize(None, [], state="s", code_verifier="v")

        self.assertEqual(handler.records, [])


@override_settings(SOCIAL_PROVIDER_MODE="official")
class GetProviderInstrumentationTests(TestCase):
    def test_instrumentation_preserves_the_adapter_type(self):
        # Callers rely on `isinstance(provider, OfficialXProvider)`; wrapping the
        # instance (not the object) is what keeps that true.
        provider = get_provider("x")
        self.assertIsInstance(provider, OfficialXProvider)
        self.assertEqual(provider.platform, "x")

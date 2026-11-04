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
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REQUIREMENTS_DIR = Path(__file__).resolve().parent.parent / "requirements"


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


def _normalize(name):
    """PEP 503 name equality: case-insensitive, and `-`, `_`, `.` all collapse."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _input_requirement_names(path):
    """Top-level names in a requirements input, following `-r` includes."""
    names = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(("-r", "--requirement")):
            names |= _input_requirement_names(path.parent / line.split(None, 1)[1].strip())
            continue
        if line.startswith("-"):
            continue
        names.add(_normalize(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0]))
    return names


def _locked_names(path):
    """Names pinned by a compiled lock file (top-level `name==version` lines)."""
    names = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw[0] in " #":
            continue
        if "==" in raw:
            names.add(_normalize(raw.split("==", 1)[0]))
    return names


class RequirementLockTests(SimpleTestCase):
    """The locks the image and CI install, checked against the inputs they came from.

    `requirements/*.txt` are hand-edited inputs (names and lower bounds);
    `requirements/lock/*.txt` are what is actually installed. Editing an input
    and forgetting to recompile is the same class of failure as the 2026-11-04
    outage: the diff shows one intent and the runtime does another. A lock is
    only worth having if it cannot silently fall behind its input.
    """

    def test_every_input_requirement_is_locked(self):
        for name in ("dev", "prod"):
            with self.subTest(lock=name):
                expected = _input_requirement_names(REQUIREMENTS_DIR / f"{name}.txt")
                locked = _locked_names(REQUIREMENTS_DIR / "lock" / f"{name}.txt")
                missing = expected - locked
                self.assertFalse(
                    missing,
                    f"{name} lock is missing {sorted(missing)}; "
                    "re-run scripts/compile_requirements.sh",
                )

    def test_locks_pin_every_requirement(self):
        """A lock with a range in it is an input wearing a lock's name."""
        for name in ("dev", "prod"):
            with self.subTest(lock=name):
                lines = (
                    REQUIREMENTS_DIR / "lock" / f"{name}.txt"
                ).read_text(encoding="utf-8").splitlines()
                unpinned = [
                    line
                    for line in lines
                    if line.strip() and line[0] not in " #" and "==" not in line
                ]
                self.assertFalse(unpinned, f"{name} lock has unpinned lines: {unpinned}")

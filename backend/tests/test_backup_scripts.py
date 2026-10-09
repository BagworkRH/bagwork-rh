"""Backup/restore scripts stay valid and their spot-checks match the schema.

A drift test, not a Postgres test: it proves the shell is well-formed and that
every table the restore drill compares still exists, so a renamed table does not
turn the drill into a false "PASS".
"""
import re
import shutil
import subprocess
from pathlib import Path

from django.db import connection
from django.test import TestCase

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
BACKUP = SCRIPT_DIR / "backup_db.sh"
RESTORE = SCRIPT_DIR / "restore_db.sh"
VERIFY = SCRIPT_DIR / "verify_restore.sh"

# Lines inside `SPOT_CHECKS=( ... )` shaped `"table:label"`.
SPOT_CHECK_RE = re.compile(r'^\s*"([a-z0-9_]+):[^"]*"\s*$', re.MULTILINE)


def _working_bash():
    """Path to a usable bash, or None.

    `shutil.which("bash")` is not enough on Windows: it can resolve to the WSL
    stub, which exists but cannot run. Probe with a trivial script.
    """
    bash = shutil.which("bash")
    if bash is None:
        return None
    try:
        probe = subprocess.run(
            [bash, "-c", "echo bash-ok"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bash if probe.stdout.strip() == "bash-ok" else None


class ScriptPresenceTests(TestCase):
    def test_the_scripts_exist(self):
        for path in (BACKUP, RESTORE, VERIFY):
            self.assertTrue(path.is_file(), f"{path} is missing")


class ScriptSyntaxTests(TestCase):
    def test_scripts_are_valid_bash(self):
        bash = _working_bash()
        if bash is None:
            self.skipTest("no usable bash available")
        for path in (BACKUP, RESTORE, VERIFY):
            result = subprocess.run(
                [bash, "-n", str(path)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


class SpotCheckSyncTests(TestCase):
    def test_drill_spot_checks_reference_real_tables(self):
        tables = SPOT_CHECK_RE.findall(VERIFY.read_text(encoding="utf-8"))
        self.assertTrue(tables, "no SPOT_CHECKS found in verify_restore.sh")
        known = set(connection.introspection.table_names())
        missing = [t for t in tables if t not in known]
        self.assertEqual(missing, [], f"spot-check tables not in the schema: {missing}")

    def test_backup_script_supports_the_check_flag(self):
        self.assertIn("--check", BACKUP.read_text(encoding="utf-8"))

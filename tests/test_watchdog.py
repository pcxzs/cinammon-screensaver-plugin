"""The watchdog must fail closed: never kill a locked screensaver unprotected."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

try:
    import gi
    gi.require_version("GLib", "2.0")
    from cinnamon_screensaver_video import watchdog
    HAVE_GI = True
except ImportError:
    HAVE_GI = False


@unittest.skipUnless(HAVE_GI, "PyGObject not available")
class TerminationPolicyTests(unittest.TestCase):

    def setUp(self):
        self.saved = sys.modules.get("status")

    def tearDown(self):
        if self.saved is None:
            sys.modules.pop("status", None)
        else:
            sys.modules["status"] = self.saved

    def set_locked(self, value):
        sys.modules["status"] = types.SimpleNamespace(Locked=value)

    def test_unknown_state_is_not_safe(self):
        sys.modules.pop("status", None)
        self.assertFalse(watchdog._safe_to_terminate())
        sys.modules["status"] = types.SimpleNamespace()
        self.assertFalse(watchdog._safe_to_terminate())

    def test_unlocked_is_safe(self):
        self.set_locked(False)
        self.assertTrue(watchdog._safe_to_terminate())

    def test_locked_without_backup_locker_is_not_safe(self):
        self.set_locked(True)
        self.assertFalse(watchdog._backup_locker_running())
        self.assertFalse(watchdog._safe_to_terminate())

    def test_locked_with_backup_locker_child_is_safe(self):
        tmp = tempfile.mkdtemp()
        fake = os.path.join(tmp, watchdog.BACKUP_LOCKER)
        shutil.copy(shutil.which("sleep"), fake)
        child = subprocess.Popen([fake, "30"])
        try:
            time.sleep(0.2)
            self.set_locked(True)
            self.assertTrue(watchdog._backup_locker_running())
            self.assertTrue(watchdog._safe_to_terminate())
        finally:
            child.kill()
            child.wait()
            shutil.rmtree(tmp)


@unittest.skipUnless(HAVE_GI, "PyGObject not available")
class StallTests(unittest.TestCase):

    def run_stall(self, stall_seconds, locked):
        code = (
            "import sys, types, time\n"
            "from gi.repository import GLib\n"
            "from cinnamon_screensaver_video import watchdog\n"
            "watchdog.STALL_DUMP, watchdog.STALL_EXIT = 1, 3\n"
            "sys.modules['status'] = types.SimpleNamespace(Locked=%r)\n"
            "watchdog.start()\n"
            "loop = GLib.MainLoop()\n"
            "def stall():\n"
            "    time.sleep(%r)\n"
            "    GLib.timeout_add(2500, loop.quit)  # let the watchdog see the recovery\n"
            "    return False\n"
            "GLib.timeout_add(200, stall)\n"
            "loop.run()\n"
            "print('survived')\n" % (locked, stall_seconds))
        from tests import run_python
        return run_python(code)

    def test_stall_dumps_and_recovers(self):
        r = self.run_stall(2, locked=True)
        self.assertEqual(r.stdout.strip(), "survived", r.stderr)
        self.assertIn("dumping stacks", r.stderr)
        self.assertIn("recovered", r.stderr)

    def test_locked_without_backup_locker_fails_closed(self):
        r = self.run_stall(5, locked=True)
        self.assertEqual(r.stdout.strip(), "survived", r.stderr)
        self.assertIn("failing closed", r.stderr)

    def test_unlocked_hang_is_terminated(self):
        r = self.run_stall(8, locked=False)
        self.assertEqual(r.returncode, -9, r.stderr)
        self.assertIn("terminating the screensaver", r.stderr)


if __name__ == "__main__":
    unittest.main()

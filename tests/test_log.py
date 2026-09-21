"""The log file must never be a way to write somewhere unexpected."""

import os
import stat
import tempfile
import unittest

from cinnamon_screensaver_video import log


class LogTests(unittest.TestCase):

    def setUp(self):
        self.cache = tempfile.mkdtemp()
        self.old_env = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = self.cache
        log._file = None

    def tearDown(self):
        if log._file:
            log._file.close()
        log._file = None
        os.environ["XDG_CACHE_HOME"] = self.old_env

    def test_creates_private_file(self):
        log.log("hello")
        st = os.stat(log.log_path())
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(log.log_dir()).st_mode), 0o700)
        with open(log.log_path()) as f:
            self.assertIn("hello", f.read())

    def test_symlinked_file_not_followed(self):
        os.makedirs(log.log_dir(), mode=0o700)
        target = os.path.join(self.cache, "victim")
        with open(target, "w") as f:
            f.write("original\n")
        os.symlink(target, log.log_path())
        log.log("must not reach the target")
        self.assertIsNone(log.get_file())
        with open(target) as f:
            self.assertEqual(f.read(), "original\n")

    def test_symlinked_directory_not_used(self):
        elsewhere = tempfile.mkdtemp()
        os.symlink(elsewhere, log.log_dir())
        log.log("must not reach the target")
        self.assertIsNone(log.get_file())
        self.assertEqual(os.listdir(elsewhere), [])

    def test_group_writable_directory_rejected(self):
        os.makedirs(log.log_dir())
        os.chmod(log.log_dir(), 0o777)
        log.log("x")
        self.assertIsNone(log.get_file())

    def test_rotation(self):
        os.makedirs(log.log_dir(), mode=0o700)
        with open(log.log_path(), "w") as f:
            f.write("x" * (log.MAX_SIZE + 1))
        log.log("fresh")
        self.assertTrue(os.path.exists(log.log_path() + ".old"))
        with open(log.log_path()) as f:
            self.assertIn("fresh", f.read())


if __name__ == "__main__":
    unittest.main()

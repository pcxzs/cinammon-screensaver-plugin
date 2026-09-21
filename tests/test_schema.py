"""The GSettings schema compiles and has safe defaults."""

import os
import shutil
import subprocess
import unittest

from tests import ROOT

DATA = os.path.join(ROOT, "data")


@unittest.skipUnless(shutil.which("glib-compile-schemas"), "glib-compile-schemas missing")
class SchemaTests(unittest.TestCase):

    def test_compiles_strictly(self):
        subprocess.run(["glib-compile-schemas", "--strict", "--dry-run", DATA], check=True)

    def test_safe_defaults(self):
        from cinnamon_screensaver_video import config
        s = config.get_settings()
        self.assertIsNotNone(s)
        self.assertTrue(s.get_default_value("mute").unpack(), "must be muted by default")
        self.assertEqual(s.get_default_value("video-uri").unpack(), "")
        self.assertFalse(s.get_default_value("hardware-acceleration").unpack())


if __name__ == "__main__":
    unittest.main()

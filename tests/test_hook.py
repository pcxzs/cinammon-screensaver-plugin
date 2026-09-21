"""The import hook: inert everywhere except the exact, trusted targets."""

import os
import tempfile
import textwrap
import unittest

from tests import run_python

FAKE_MONITOR_VIEW = textwrap.dedent("""
    class MonitorView:
        def __init__(self, index):
            self.monitor_index = index
        def set_next_wallpaper_image(self, image):
            pass
""")

FAKE_SETTINGS_MODULE = textwrap.dedent("""
    class Module:
        def on_module_selected(self):
            pass
""")


def make_module(root, subdirs, name, source):
    d = os.path.join(root, *subdirs)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".py"), "w") as f:
        f.write(source)
    return d


class HookTests(unittest.TestCase):

    def test_import_is_lightweight(self):
        r = run_python("import cinnamon_screensaver_video.hook as h\n"
                       "print('gi' in sys.modules, any(isinstance(f, h._Finder) for f in sys.meta_path))")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["False", "True"])

    def test_install_is_idempotent(self):
        r = run_python("import cinnamon_screensaver_video.hook as h\n"
                       "h.install(); h.install()\n"
                       "print(sum(isinstance(f, h._Finder) for f in sys.meta_path))")
        self.assertEqual(r.stdout.strip(), "1", r.stderr)

    def test_pth_line_never_raises(self):
        pth = os.path.join(os.path.dirname(__file__), "..", "src", "cinnamon_screensaver_video.pth")
        with open(pth) as f:
            line = f.read().strip()
        self.assertTrue(line.startswith("import "), "site only executes lines starting with 'import'")
        # Simulate a broken/half-removed install: the import fails but must stay silent.
        r = run_python("sys.path.pop(0)\nsys.modules['cinnamon_screensaver_video'] = None\n" + line + "\nprint('ok')")
        self.assertEqual((r.returncode, r.stdout.strip(), r.stderr), (0, "ok", ""))

    def test_other_modules_ignored(self):
        from cinnamon_screensaver_video import hook
        finder = hook._Finder()
        self.assertIsNone(finder.find_spec("json"))
        self.assertIsNone(finder.find_spec("monitorView", path=["/somewhere"]))

    def test_wrong_directory_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["not-the-screensaver"], "monitorView", FAKE_MONITOR_VIEW)
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook as h\n"
                           "h._trusted_origin = lambda p: True\n"
                           "import monitorView\n"
                           "print(monitorView.MonitorView.__init__.__name__)" % d)
            self.assertEqual(r.stdout.strip(), "__init__", r.stderr)

    @unittest.skipIf(os.geteuid() == 0, "files created by root are trusted")
    def test_untrusted_file_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["cinnamon-screensaver"], "monitorView", FAKE_MONITOR_VIEW)
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook\n"
                           "import monitorView\n"
                           "print(monitorView.MonitorView.__init__.__name__)" % d)
            self.assertEqual(r.stdout.strip(), "__init__", r.stderr)

    def test_trusted_origin_rules(self):
        from cinnamon_screensaver_video import hook
        self.assertTrue(hook._trusted_origin(os.path.realpath("/usr/bin/env")))
        self.assertFalse(hook._trusted_origin("/nonexistent/file.py"))
        if os.geteuid() != 0:
            with tempfile.NamedTemporaryFile(suffix=".py") as f:
                self.assertFalse(hook._trusted_origin(f.name))

    def test_monitor_view_patched_when_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["cinnamon-screensaver"], "monitorView", FAKE_MONITOR_VIEW)
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook as h\n"
                           "h._trusted_origin = lambda p: True\n"
                           "import monitorView\n"
                           "mv = monitorView.MonitorView\n"
                           "print(mv.__init__.__name__, mv.set_next_wallpaper_image.__name__)" % d)
            self.assertEqual(r.stdout.split(), ["patched_init", "patched_set_image"], r.stderr)

    def test_disable_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["cinnamon-screensaver"], "monitorView", FAKE_MONITOR_VIEW)
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook as h\n"
                           "h._trusted_origin = lambda p: True\n"
                           "import monitorView\n"
                           "print(monitorView.MonitorView.__init__.__name__)" % d,
                           CINNAMON_SCREENSAVER_VIDEO_DISABLE="1")
            self.assertEqual(r.stdout.strip(), "__init__", r.stderr)

    def test_unsupported_monitor_view_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["cinnamon-screensaver"], "monitorView", "class Other: pass\n")
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook as h\n"
                           "h._trusted_origin = lambda p: True\n"
                           "import monitorView\n"
                           "print('loaded', hasattr(monitorView, 'Other'))" % d)
            self.assertEqual(r.stdout.strip(), "loaded True", r.stderr)
            self.assertIn("unsupported cinnamon-screensaver version", r.stderr)

    def test_settings_module_patched_when_schema_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["cinnamon-settings", "modules"], "cs_screensaver", FAKE_SETTINGS_MODULE)
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook as h\n"
                           "h._trusted_origin = lambda p: True\n"
                           "import cs_screensaver\n"
                           "print(cs_screensaver.Module.on_module_selected.__name__)" % d)
            self.assertEqual(r.stdout.strip(), "patched_selected", r.stderr)

    def test_settings_module_untouched_without_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_module(tmp, ["cinnamon-settings", "modules"], "cs_screensaver", FAKE_SETTINGS_MODULE)
            empty = os.path.join(tmp, "empty")
            os.makedirs(os.path.join(empty, "glib-2.0", "schemas"))
            r = run_python("sys.path.insert(0, %r)\n"
                           "import cinnamon_screensaver_video.hook as h\n"
                           "h._trusted_origin = lambda p: True\n"
                           "import cs_screensaver\n"
                           "print(cs_screensaver.Module.on_module_selected.__name__)" % d,
                           GSETTINGS_SCHEMA_DIR=os.path.join(empty, "glib-2.0", "schemas"),
                           XDG_DATA_DIRS=empty)
            self.assertEqual(r.stdout.strip(), "on_module_selected", r.stderr)


if __name__ == "__main__":
    unittest.main()

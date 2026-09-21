"""
Test setup, run before any test module is imported.

The suite is started with "python3 -S" so that an installed copy of the hook
(loaded through its .pth file) can't shadow the source tree. That also drops
the system dist-packages directories, so they are re-added here for PyGObject.

GSettings is pointed at a private, freshly compiled copy of the schema with an
in-memory backend, so tests never read or modify the real user's settings.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

if SRC not in sys.path:
    sys.path.insert(0, SRC)
for d in ["/usr/lib/python3/dist-packages"] + glob.glob("/usr/lib/python3.*/dist-packages"):
    if os.path.isdir(d) and d not in sys.path:
        sys.path.append(d)

SCHEMA_DIR = tempfile.mkdtemp(prefix="csv-test-schemas-")
shutil.copy(os.path.join(ROOT, "data", "org.cinnamon.screensaver-video.gschema.xml"), SCHEMA_DIR)
if shutil.which("glib-compile-schemas"):
    subprocess.run(["glib-compile-schemas", SCHEMA_DIR], check=True)
os.environ["GSETTINGS_SCHEMA_DIR"] = SCHEMA_DIR
os.environ["GSETTINGS_BACKEND"] = "memory"
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="csv-test-cache-")


def python_env(**extra):
    """Environment for child interpreters that use the source tree."""
    env = dict(os.environ)
    env.update(extra)
    return env


def run_python(code, **env):
    """Run code in a fresh "python3 -S" with the source tree and system gi on sys.path."""
    prelude = ("import sys, glob, os\n"
               "sys.path.insert(0, %r)\n"
               "sys.path += ['/usr/lib/python3/dist-packages'] + glob.glob('/usr/lib/python3.*/dist-packages')\n"
               % SRC)
    return subprocess.run([sys.executable, "-S", "-c", prelude + code],
                          env=python_env(**env), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=120)

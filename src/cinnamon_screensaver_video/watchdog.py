"""
Main-loop watchdog for the cinnamon-screensaver process.

While active, the screensaver holds the keyboard and pointer grabs, so a
stalled main loop makes the whole session look frozen. The watchdog:

  * after STALL_DUMP seconds without a main-loop heartbeat, writes Python
    stack traces of all threads to the log (plus native traces via gdb, if
    installed and the kernel's ptrace policy already permits it - the
    watchdog never relaxes that policy itself);
  * after STALL_EXIT seconds, terminates the process *only if that can't
    unlock the session*: either the screen isn't locked, or Cinnamon's
    cs-backup-locker is running as our child (it covers the screen and keeps
    the session locked when the screensaver dies). Otherwise it fails closed
    and leaves the frozen - but still locked - screensaver alone.

Time is measured with CLOCK_MONOTONIC, which doesn't advance during system
suspend, so sleeping the machine never trips it.
"""

import faulthandler
import os
import signal
import subprocess
import sys
import threading
import time

from gi.repository import GLib

from cinnamon_screensaver_video.log import log, get_file

HEARTBEAT_MS = 1000
STALL_DUMP = 10
STALL_EXIT = 30

GDB = "/usr/bin/gdb"
BACKUP_LOCKER = "cs-backup-locker"
PTRACE_SCOPE = "/proc/sys/kernel/yama/ptrace_scope"

_started = False
_last_beat = time.monotonic()


def _beat():
    global _last_beat
    _last_beat = time.monotonic()
    return GLib.SOURCE_CONTINUE


def _ptrace_allowed():
    """True if a child process may attach to us without any prctl() changes."""
    try:
        with open(PTRACE_SCOPE) as f:
            return f.read().strip() == "0"
    except OSError:
        return True  # no Yama LSM: classic same-uid ptrace rules apply


def _dump_native_stacks():
    if not os.access(GDB, os.X_OK) or not _ptrace_allowed():
        return
    try:
        out = subprocess.run([GDB, "-nx", "-batch", "-p", str(os.getpid()),
                              "-ex", "info threads",
                              "-ex", "thread apply all bt 30"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=60, text=True).stdout
        log("watchdog: native stacks:\n%s" % out)
    except Exception as e:
        log("watchdog: gdb failed: %r" % e)


def _screen_locked():
    """cinnamon-screensaver's own lock flag; None if it can't be determined."""
    status = sys.modules.get("status")
    locked = getattr(status, "Locked", None)
    return locked if isinstance(locked, bool) else None


def _backup_locker_running():
    me = os.getpid()
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return False
    for pid in pids:
        try:
            with open("/proc/%s/stat" % pid) as f:
                # "pid (comm) state ppid ..." - comm may contain spaces/parens
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            if ppid != me:
                continue
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                argv0 = f.read().split(b"\0", 1)[0].decode(errors="replace")
            if os.path.basename(argv0) == BACKUP_LOCKER:
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def _safe_to_terminate():
    locked = _screen_locked()
    if locked is False:
        return True
    if locked is True:
        return _backup_locker_running()
    return False


def _run():
    dumped = False
    refused = False
    while True:
        time.sleep(1)
        stalled = time.monotonic() - _last_beat
        if stalled < STALL_DUMP:
            if dumped:
                log("watchdog: main loop recovered after stall")
            dumped = refused = False
            continue

        if not dumped:
            dumped = True
            log("watchdog: main loop blocked for %ds, dumping stacks" % stalled)
            f = get_file()
            if f is not None:
                try:
                    f.flush()
                    faulthandler.dump_traceback(file=f, all_threads=True)
                    f.flush()
                except Exception:
                    pass
            _dump_native_stacks()

        if time.monotonic() - _last_beat < STALL_EXIT:
            continue

        if _safe_to_terminate():
            log("watchdog: main loop blocked for %ds, terminating the screensaver" % STALL_EXIT)
            os.kill(os.getpid(), signal.SIGKILL)
        elif not refused:
            refused = True
            log("watchdog: main loop blocked for %ds, but the screen is locked and no "
                "backup locker is running; not terminating (failing closed)" % STALL_EXIT)


def start():
    """Start the watchdog once per process. Must be called from the main thread."""
    global _started
    if _started:
        return
    _started = True
    _beat()
    GLib.timeout_add(HEARTBEAT_MS, _beat)
    threading.Thread(target=_run, name="csv-watchdog", daemon=True).start()
    log("watchdog started")

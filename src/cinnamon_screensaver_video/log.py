"""
Logging for the processes the hook activates in.

cinnamon-screensaver is D-Bus activated, so its stdout often isn't kept
anywhere. Messages are therefore also appended to
$XDG_CACHE_HOME/cinnamon-screensaver-video/log (default ~/.cache/...).

The file is opened defensively: this code may run in a process whose HOME
points at another user's directory (e.g. a settings tool started via sudo),
so symlinks are never followed and the directory and file must belong to the
effective user. If anything looks wrong, file logging is silently disabled.
"""

import os
import stat
import sys
import time

MAX_SIZE = 512 * 1024

_file = None


def log_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "cinnamon-screensaver-video")


def log_path():
    return os.path.join(log_dir(), "log")


def _owned_by_me(st):
    return st.st_uid == os.geteuid()


def _open_log():
    directory = log_dir()
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    except OSError:
        return None

    st = os.lstat(directory)
    if not stat.S_ISDIR(st.st_mode) or not _owned_by_me(st) or st.st_mode & 0o022:
        return None

    path = log_path()
    try:
        st = os.lstat(path)
        if stat.S_ISREG(st.st_mode) and _owned_by_me(st) and st.st_size > MAX_SIZE:
            os.replace(path, path + ".old")
    except FileNotFoundError:
        pass

    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags, 0o600)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or not _owned_by_me(st):
        os.close(fd)
        return None
    return os.fdopen(fd, "a", buffering=1)


def get_file():
    """The open (append, line-buffered) log file, or None if unavailable."""
    global _file
    if _file is None:
        try:
            _file = _open_log() or False
        except OSError:
            _file = False
    return _file or None


def log(msg):
    line = "cinnamon-screensaver-video: %s" % msg
    print(line, file=sys.stderr, flush=True)
    f = get_file()
    if f is not None:
        try:
            f.write("%s [%d] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), msg))
        except OSError:
            pass

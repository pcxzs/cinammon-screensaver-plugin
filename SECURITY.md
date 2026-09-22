# Security

This package runs code inside the **screen locker**, and its hook is loaded by
**every Python 3 process** on the system. Both are sensitive places, so the
design goal is: *add no new way to bypass the lock, escalate privileges, or
make unrelated programs misbehave.*

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) for this
repository, or contact the maintainer listed in `debian/control`. Include the
Cinnamon and cinnamon-screensaver versions, your distribution, and steps to
reproduce. You should get a reply within a week.

## Threat model

**In scope**

- Someone with physical access to a locked session trying to get past the lock.
- Another local user trying to influence a victim's screensaver or gain the
  victim's (or root's) privileges through this package.
- Unprivileged code tricking the hook into running in privileged processes.
- The lock screen being made to contact the network.

**Out of scope**

- Code already running as the *same* user. It can change the user's settings,
  kill or replace the screensaver, or read the session anyway; the lock screen
  protects against physical access, not against the user's own processes.
- Bugs in GStreamer decoders themselves (see *Media parsing* below).

## Measures

| Area | Risk | Mitigation |
|---|---|---|
| `.pth` hook in every Python process | Slows down or breaks unrelated programs, including ones running as root | The hook only imports `os`/`sys` and registers a finder. The `.pth` line catches every exception, so it can't print errors or abort start-up. Everything else is imported lazily inside the two target processes only. |
| Module targeting | A user-writable `monitorView.py` gets patched, or the hook activates in the wrong program | Exact module names only, from the expected directories only, and only if the file and its directory are root-owned and not group/world-writable. |
| Lock bypass through the watchdog | Terminating a frozen screensaver could reveal the desktop | The screensaver is only terminated if it isn't locked, or if Cinnamon's `cs-backup-locker` is running as its child (that locker keeps the session locked). Otherwise the watchdog fails closed and only logs. |
| Weakened ptrace protection | Debug stack dumps would need `PR_SET_PTRACER`, which lets other processes attach to the locker | Never changed. Native stack traces are only taken with `/usr/bin/gdb` (absolute path, `-nx`) when `kernel.yama.ptrace_scope` is already 0. |
| Log file symlink attacks | A privileged process with a user's `$HOME` could be tricked into writing through a symlink | The log directory and file are opened with `O_NOFOLLOW`, must be owned by the effective user and not group/world-writable, and are created with modes 0700 and 0600. Otherwise logging to file is silently disabled. |
| Network access from the lock screen | A URI or a playlist disguised as a video (HLS/DASH/SDP) makes the locker fetch URLs or listen on sockets | Only local, regular, readable files are accepted (`file://` or an absolute path). Network-capable GStreamer elements (adaptive demuxers, SDP/RTSP/HTTP/UDP/TCP/RTMP/SRT/RIST sources, webrtcbin) are disabled for autoplugging inside the process. Subtitle autoloading is off. |
| Main-thread hangs | A blocked main loop freezes a session that holds the input grabs | The main thread never changes pipeline state or seeks: every such call runs on one worker thread per pipeline, so a GStreamer deadlock can only freeze the video. Looping uses segment seeks instead of playbin's gapless group switching, which deadlocked against concurrent state changes when audio was enabled (regression-tested). State changes are only issued when the target changes. The UPower connection is asynchronous. |
| Audio from a locked machine | Unexpected sound | Muted by default. When enabled, sound comes from one monitor only. |

## Media parsing

The video is decoded inside the lock screen process by GStreamer and
whichever decoder plugins are installed (e.g. libav). A crafted video file
that exploits a decoder bug would run code with the user's privileges, the
same as opening it in any video player. Only use videos from sources you
trust, and keep GStreamer and its plugins up to date.

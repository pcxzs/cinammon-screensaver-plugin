# cinnamon-screensaver-video

Play a looping video (MP4, WebM, MKV — anything GStreamer can decode) as the
background of the **Cinnamon screensaver and lock screen**, in place of the
wallpaper.

Everything else stays Cinnamon's own: the unlock dialog, clock, away message,
password check (PAM), idle and lock timers, multi-monitor handling and the
crash-safe backup locker. This is not a separate screen locker.

- Settings live in **System Settings → Screensaver → Video**
- Video plays on every monitor; sound (off by default) on the primary one only
- Fill (crop), fit (letterbox) or stretch; adjustable darkening so the clock stays readable
- Pauses while monitors are powered off; optional still frame on battery
- Falls back to the normal wallpaper if the video can't be played
- Doesn't modify any file of Cinnamon or cinnamon-screensaver

> **Status:** 0.9 — feature complete, looking for testers on more distributions
> and Cinnamon versions. Developed and tested on Debian 13 with Cinnamon 6.6 /
> cinnamon-screensaver 6.6 (X11).

## Requirements

- Cinnamon with cinnamon-screensaver (X11; cinnamon-screensaver doesn't run on Wayland)
- Python 3.8+, PyGObject, GTK 3
- GStreamer 1.x with the base and good plugins, the GTK3 video sink
  (`gstreamer1.0-gtk3` on Debian/Ubuntu), and a decoder for your video's codec
  (e.g. `gstreamer1.0-libav` for H.264 MP4)

## Install

### Debian, Ubuntu, Linux Mint, LMDE

Download the `.deb` from the [releases page](../../releases), or build it:

```sh
sudo apt install debhelper dh-python        # optional, for the full Debian build
make deb                                    # -> dist/cinnamon-screensaver-video_0.9.0_all.deb
sudo apt install ./dist/cinnamon-screensaver-video_0.9.0_all.deb
cinnamon-screensaver-command --exit         # restart the screensaver once
```

### Other distributions

Install the dependencies listed above with your package manager, then:

```sh
sudo make install        # auto-detects the Python site-packages dir; override with PYTHONDIR=...
cinnamon-screensaver-command --exit
```

## Usage

Open **System Settings → Screensaver**, switch to the **Video** tab (next to
*Settings* and *Customize*) and pick a video file. You can also run
`cinnamon-settings screensaver -t 2`.

| Setting | Meaning |
|---|---|
| Play a video … | turn the feature on or off |
| Video file | a local video file to loop |
| Scaling | *Fill* (crop to cover), *Fit* (black borders), *Stretch* |
| Darken | dim the video so the clock and dialog stay readable (default 30%) |
| Mute / Volume | sound plays on the primary monitor only; muted by default |
| Pause while the monitors are powered off | stop decoding while the screens are in standby |
| Show a still frame while on battery | save power on laptops |
| Use OpenGL rendering | `gtkglsink`; can lower CPU use on high-resolution monitors |

Changes apply the next time the screensaver starts. The **Preview** button (or
`cinnamon-screensaver-video-preview [file]`) plays the video full screen the
same way the lock screen does; press Esc to close it.

From the command line:

```sh
gsettings set org.cinnamon.screensaver-video video-uri "file://$HOME/Videos/loop.mp4"
gsettings list-recursively org.cinnamon.screensaver-video
```

## How it works

cinnamon-screensaver has no plugin API, and Cinnamon applets or extensions run
in a different process, so they can't draw on the lock screen. This package
therefore installs a one-line `cinnamon_screensaver_video.pth` file into the
system Python path, which imports a tiny hook
(`cinnamon_screensaver_video/hook.py`) in every Python process. The hook only
registers an import finder that ignores every import except two:

- **`monitorView`** from cinnamon-screensaver's directory: after the real
  module loads, `MonitorView` is wrapped so each monitor gets a GStreamer
  `playbin → gtksink` widget in the wallpaper's place. Frames are scaled and
  cropped to the monitor's size inside GStreamer, looping is gapless, and the
  pipeline is shut down when the screen is unlocked.
- **`cs_screensaver`** from cinnamon-settings' modules directory: a *Video*
  tab is added to the stock Screensaver settings page.

Both are only patched when loaded from root-owned, non-world-writable files.
If Cinnamon changes these internals, the hook logs a message and steps aside.
The screensaver then behaves exactly as without this package.

## Troubleshooting

- **Log:** `~/.cache/cinnamon-screensaver-video/log` records why a video was
  or wasn't played, playback errors, and watchdog reports.
- **Debug run:** `cinnamon-screensaver-command --exit; cinnamon-screensaver --debug --hold`
- **Turn the hook off for one run:** start the screensaver with
  `CINNAMON_SCREENSAVER_VIDEO_DISABLE=1` in its environment.
- **Watchdog:** the screensaver holds the keyboard and mouse while active, so a
  stalled main loop would make the session look frozen. After 10 s the plugin
  logs stack traces. After 30 s it terminates the screensaver, but only when
  that can't expose your session: when the screen isn't locked, or when
  Cinnamon's backup locker is running. The backup locker keeps the session
  locked; follow its on-screen instructions (switch to a text console, run
  `cinnamon-unlock-desktop`, switch back). If neither is true, it leaves the
  locked screen alone.
- **Black background with "Use OpenGL rendering":** turn that option off.

## Uninstall

```sh
sudo apt remove cinnamon-screensaver-video     # or: sudo make uninstall
cinnamon-screensaver-command --exit
```

## Development

```sh
make test          # unit tests; the playback tests need a display (xvfb-run make test)
make lint          # pyflakes + strict schema check
make deb           # build the .deb
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and
[docs/PUBLISHING.md](docs/PUBLISHING.md).

## License

GPL-2.0-or-later, the same license as cinnamon-screensaver. See [LICENSE](LICENSE).

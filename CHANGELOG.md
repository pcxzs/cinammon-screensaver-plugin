# Changelog

## 0.9.0 — first public release

- Looping video background for the Cinnamon screensaver and lock screen, on
  every monitor, via an import hook (no Cinnamon files modified).
- "Video" tab on the Screensaver page of System Settings.
- Fill / fit / stretch scaling, darkening, optional sound on the primary monitor.
- Pauses while monitors are powered off; optional still frame on battery.
- Falls back to the wallpaper on any error; logs to
  `~/.cache/cinnamon-screensaver-video/log`.
- Main-loop watchdog with stack dumps; fail-closed termination that relies on
  Cinnamon's backup locker.
- Hardening: local regular files only, network-capable GStreamer elements
  disabled, symlink-safe logging, hook only activates for root-owned modules.
- `cinnamon-screensaver-video-preview` tool.

# Contributing

Bug reports, testing on other distributions and Cinnamon versions, and patches
are welcome.

## Reporting bugs

Please include:

- distribution and version, Cinnamon and cinnamon-screensaver versions
  (`cinnamon --version`, `cinnamon-screensaver --version`)
- the video's codec/container (`gst-discoverer-1.0 file.mp4`)
- the last lines of `~/.cache/cinnamon-screensaver-video/log`
- output of a debug run: `cinnamon-screensaver-command --exit; cinnamon-screensaver --debug --hold`

Remove personal paths or file names from logs before posting them.

For security issues, see [SECURITY.md](SECURITY.md) instead.

## Development

```sh
make test            # unit tests (python3 -S, isolated GSettings)
xvfb-run make test   # include the playback tests that need a display
make lint            # pyflakes and strict schema compile
make deb             # build the .deb into dist/
```

Try a change against the real screensaver without installing it:

```sh
cinnamon-screensaver-command --exit
PYTHONPATH=$PWD/src cinnamon-screensaver --debug --hold --disable-locking
cinnamon-screensaver-command -a     # activate; move the mouse to end it
```

Guidelines:

- `hook.py` runs in every Python process: keep it to `os`/`sys`, no I/O at import.
- Never block the screensaver's main thread; it holds the input grabs. Don't call
  `set_state()`/`seek()` on a pipeline from it - go through `LoopingPlayer`.
- Fail safe: on any unexpected condition, fall back to the stock behaviour.
- Match the surrounding style; add a test for behaviour changes.
- Add an entry to `CHANGELOG.md` and `debian/changelog` (`dch -i`) for user-visible changes.

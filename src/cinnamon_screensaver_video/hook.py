"""
Import hook that activates cinnamon-screensaver-video.

This module is imported at interpreter start-up (via
cinnamon_screensaver_video.pth) by *every* Python 3 process on the system, so
it must stay tiny, side-effect free and impossible to break:

  * it only imports ``os`` and ``sys``;
  * it only registers a meta-path finder;
  * the finder ignores every import except two exact top-level module names,
    and only when they are loaded from a root-owned, non-world-writable file
    inside the expected directory:

      - ``monitorView`` from ``.../cinnamon-screensaver/``: MonitorView is
        wrapped so each monitor shows a looping video instead of the
        wallpaper (see ``_patch_monitor_view``);
      - ``cs_screensaver`` from ``.../cinnamon-settings/modules/``: a "Video"
        tab is added to Cinnamon's Screensaver settings page.

The real module is always loaded unmodified first; the patch only wraps it.
Any failure while patching is logged and leaves the stock behaviour intact.

Set CINNAMON_SCREENSAVER_VIDEO_DISABLE=1 in a process's environment to turn
the hook off for that process.
"""

import os
import sys

DISABLE_ENV = "CINNAMON_SCREENSAVER_VIDEO_DISABLE"

# module name -> required trailing path components of its directory
TARGETS = {
    "monitorView": ("cinnamon-screensaver",),
    "cs_screensaver": ("cinnamon-settings", "modules"),
}

# Directory containing this package. Some hosts prune sys.path after start-up
# (cinnamon-settings drops /usr/local/...), so it is re-added before the
# package's other modules are imported.
_PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_importable():
    if _PACKAGE_PARENT not in sys.path:
        sys.path.append(_PACKAGE_PARENT)


def _log(msg):
    try:
        _ensure_importable()
        from cinnamon_screensaver_video.log import log
        log(msg)
    except Exception:
        print("cinnamon-screensaver-video: %s" % msg, file=sys.stderr, flush=True)


def _trusted_origin(path):
    """
    Only patch code that an unprivileged user can't have placed or modified:
    the file and its directory must be owned by root and not writable by
    group or others.
    """
    try:
        for p in (path, os.path.dirname(path)):
            st = os.stat(p)
            if st.st_uid != 0 or st.st_mode & 0o022:
                return False
        return True
    except OSError:
        return False


class _PatchingLoader:
    """Wraps the real loader and patches the module after it has executed."""

    def __init__(self, real_loader, patch):
        self.real_loader = real_loader
        self.patch = patch

    def create_module(self, spec):
        return self.real_loader.create_module(spec)

    def exec_module(self, module):
        self.real_loader.exec_module(module)
        try:
            _ensure_importable()
            self.patch(module)
        except Exception as e:
            _log("not activated, could not patch %s: %r" % (module.__name__, e))


class _Finder:
    def __init__(self):
        self._busy = False

    def find_spec(self, fullname, path=None, target=None):
        tail = TARGETS.get(fullname)
        if tail is None or path is not None or self._busy:
            return None
        if os.environ.get(DISABLE_ENV):
            return None

        import importlib.machinery
        self._busy = True
        try:
            spec = importlib.machinery.PathFinder.find_spec(fullname, sys.path)
        finally:
            self._busy = False

        if spec is None or not spec.origin or spec.loader is None:
            return None
        parts = os.path.normpath(os.path.dirname(spec.origin)).split(os.sep)
        if tuple(parts[-len(tail):]) != tail:
            return None
        if not _trusted_origin(spec.origin):
            return None

        patch = _patch_monitor_view if fullname == "monitorView" else _patch_settings_module
        spec.loader = _PatchingLoader(spec.loader, patch)
        return spec


def _patch_monitor_view(module):
    """Show a video instead of the wallpaper on each cinnamon-screensaver monitor."""
    MonitorView = getattr(module, "MonitorView", None)
    if MonitorView is None or not hasattr(MonitorView, "set_next_wallpaper_image"):
        _log("unsupported cinnamon-screensaver version, not activating")
        return

    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk
    from cinnamon_screensaver_video import player, watchdog

    orig_init = MonitorView.__init__
    orig_set_image = MonitorView.set_next_wallpaper_image

    def fall_back(self):
        video = getattr(self, "_csv_video", None)
        self._csv_video = None
        if video is not None:
            try:
                video.get_parent().remove(video)
            except Exception:
                pass
            video.destroy()
        image = getattr(self, "_csv_wallpaper", None)
        self._csv_wallpaper = None
        if image is not None:
            orig_set_image(self, image)

    def on_video_error(video, self):
        _log("falling back to the wallpaper on monitor %d" % self.monitor_index)
        fall_back(self)
        return False

    def patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self._csv_video = None
        self._csv_wallpaper = None
        try:
            watchdog.start()
        except Exception as e:
            _log("could not start watchdog: %r" % e)
        try:
            screen = Gdk.Screen.get_default()
            index = self.monitor_index
            scale = screen.get_monitor_scale_factor(index) or 1
            video = player.create_from_settings(self.rect.width * scale,
                                                self.rect.height * scale,
                                                audio_allowed=(index == screen.get_primary_monitor()))
            if video is None:
                return
            video.set_error_callback(lambda v: on_video_error(v, self))
            video.show()
            stack = self.wallpaper_stack
            stack.add(video)
            stack.set_visible_child(video)
            self._csv_video = video
            _log("playing %r on monitor %d" % (video.uri, index))
        except Exception as e:
            _log("could not start video, using wallpaper: %r" % e)
            self._csv_video = None

    def patched_set_image(self, image):
        if getattr(self, "_csv_video", None) is not None:
            # Keep the wallpaper in case the video fails later.
            self._csv_wallpaper = image
            return
        orig_set_image(self, image)

    MonitorView.__init__ = patched_init
    MonitorView.set_next_wallpaper_image = patched_set_image


def _patch_settings_module(module):
    """Add a "Video" tab to Cinnamon's Screensaver settings page."""
    Module = getattr(module, "Module", None)
    if Module is None or not hasattr(Module, "on_module_selected"):
        _log("unsupported cinnamon-settings version, no Video tab")
        return

    from cinnamon_screensaver_video import config
    if config.get_settings() is None:
        _log("schema %s not installed, no Video tab" % config.SCHEMA_ID)
        return

    orig_selected = Module.on_module_selected

    def patched_selected(self, *args, **kwargs):
        orig_selected(self, *args, **kwargs)
        if getattr(self, "_csv_tab_added", False):
            return
        try:
            stack = getattr(self.sidePage, "stack", None)
            if stack is None:
                _log("Screensaver page has no stack, no Video tab")
                return
            from cinnamon_screensaver_video import settings_page
            stack.add_titled(settings_page.build_page(), settings_page.PAGE_NAME, settings_page._("Video"))
            self._csv_tab_added = True
        except Exception as e:
            _log("could not add the Video tab: %r" % e)

    Module.on_module_selected = patched_selected


def install():
    """Register the finder once per interpreter."""
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())


install()

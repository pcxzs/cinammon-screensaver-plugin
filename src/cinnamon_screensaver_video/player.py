"""
VideoWidget: a looping GStreamer video rendered into a Gtk widget.

Used inside cinnamon-screensaver (as each MonitorView's background) and by the
standalone preview tool. Frames are scaled/cropped to the target size inside
GStreamer, so the Gtk sink only ever paints 1:1.

Hardening, since this runs inside the lock screen:
  * only local regular files are played - no network URIs;
  * GStreamer elements that can reach the network on their own (adaptive
    streaming demuxers that follow URLs in playlists, SDP/RTSP, HTTP and
    other network sources) are disabled for autoplugging in this process;
  * no call that may block on a GStreamer streaming thread (state change to
    NULL, flushing seek) is made from the Gtk main thread.
"""

import ctypes
import ctypes.util
import threading

import gi
gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gst, Gtk, Gio, GLib

from cinnamon_screensaver_video import config
from cinnamon_screensaver_video.log import log

# GstPlayFlags
FLAG_VIDEO = 1 << 0
FLAG_AUDIO = 1 << 1
FLAG_SOFT_VOLUME = 1 << 4

DPMS_POLL_SECONDS = 3

# Elements that fetch or listen on the network by themselves when autoplugged
# from a local file (e.g. an HLS/DASH manifest or SDP file renamed to .mp4).
NETWORK_ELEMENTS = (
    "hlsdemux", "hlsdemux2", "dashdemux", "dashdemux2", "mssdemux", "mssdemux2",
    "sdpdemux", "rtspsrc", "rtspsrc2", "souphttpsrc", "curlhttpsrc", "udpsrc",
    "tcpclientsrc", "rtmpsrc", "rtmp2src", "srtsrc", "ristsrc", "webrtcbin",
)

_initialized = False


def init():
    """Initialise GStreamer once and disable network-capable elements."""
    global _initialized
    if _initialized:
        return
    Gst.init(None)
    registry = Gst.Registry.get()
    for name in NETWORK_ELEMENTS:
        factory = registry.lookup_feature(name)
        if factory is not None:
            factory.set_rank(Gst.Rank.NONE)
    _initialized = True


def to_uri(path_or_uri):
    """
    Return a file:// URI for a local path or file:// URI, or None for anything
    else (empty, relative, or non-file schemes such as http://).
    """
    if not path_or_uri:
        return None
    if path_or_uri.startswith("file://"):
        f = Gio.File.new_for_uri(path_or_uri)
    elif path_or_uri.startswith("/"):
        f = Gio.File.new_for_path(path_or_uri)
    else:
        return None
    return f.get_uri() if f.get_path() is not None else None


def is_playable_file(uri):
    """True if uri names an existing, readable, regular local file."""
    f = Gio.File.new_for_uri(uri)
    if f.get_path() is None:
        return False
    try:
        info = f.query_info("standard::type,access::can-read", Gio.FileQueryInfoFlags.NONE, None)
    except GLib.Error:
        return False
    return (info.get_file_type() == Gio.FileType.REGULAR and
            info.get_attribute_boolean("access::can-read"))


class _Dpms:
    """Minimal libXext wrapper to find out whether the monitors are powered down."""

    def __init__(self):
        self.dpy = None
        try:
            x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
            xext = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xext") or "libXext.so.6")
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            xext.DPMSCapable.argtypes = [ctypes.c_void_p]
            xext.DPMSInfo.argtypes = [ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_ushort),
                                      ctypes.POINTER(ctypes.c_ubyte)]
            dpy = x11.XOpenDisplay(None)
            if dpy and xext.DPMSCapable(dpy):
                self.x11, self.xext, self.dpy = x11, xext, dpy
            elif dpy:
                x11.XCloseDisplay(dpy)
        except Exception as e:
            log("DPMS detection unavailable: %s" % e)

    def screen_off(self):
        if not self.dpy:
            return False
        level = ctypes.c_ushort(0)
        enabled = ctypes.c_ubyte(0)
        self.xext.DPMSInfo(self.dpy, ctypes.byref(level), ctypes.byref(enabled))
        return bool(enabled.value) and level.value != 0  # 0 == DPMSModeOn

    def close(self):
        if self.dpy:
            self.x11.XCloseDisplay(self.dpy)
            self.dpy = None


class _Battery:
    """Watches UPower's OnBattery property (connects asynchronously)."""

    def __init__(self, callback):
        self.proxy = None
        self.handler = 0
        self.callback = callback
        self.cancellable = Gio.Cancellable()
        Gio.DBusProxy.new_for_bus(Gio.BusType.SYSTEM,
                                  Gio.DBusProxyFlags.DO_NOT_AUTO_START,
                                  None,
                                  "org.freedesktop.UPower",
                                  "/org/freedesktop/UPower",
                                  "org.freedesktop.UPower",
                                  self.cancellable,
                                  self._on_proxy_ready)

    def _on_proxy_ready(self, source, result):
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error as e:
            if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                log("UPower unavailable: %s" % e.message)
            return
        self.handler = self.proxy.connect("g-properties-changed", lambda *a: self.callback())
        self.callback()

    def on_battery(self):
        if self.proxy is None:
            return False
        v = self.proxy.get_cached_property("OnBattery")
        return bool(v and v.unpack())

    def close(self):
        self.cancellable.cancel()
        if self.proxy is not None:
            self.proxy.disconnect(self.handler)
            self.proxy = None


def _stop_pipeline_async(pipeline):
    """
    Shut a pipeline down without blocking the Gtk main thread.

    set_state(NULL) waits for the streaming threads to finish, and a streaming
    thread may itself be waiting for the main loop (gtksink hands work to it).
    Doing that wait on the main thread can deadlock the screensaver while it
    holds the keyboard/pointer grabs, so it's done on a worker thread instead.
    """
    def stop():
        start = GLib.get_monotonic_time()
        pipeline.set_state(Gst.State.NULL)
        took = (GLib.get_monotonic_time() - start) / 1e6
        if took > 2:
            log("pipeline shutdown took %.1fs" % took)

    threading.Thread(target=stop, name="csv-stop", daemon=True).start()


def make_filter(scaling, width, height):
    """
    A video-filter bin that outputs exactly width x height, square pixels:
    "fill" crops to the target aspect ratio, "fit" letterboxes, "stretch"
    distorts.
    """
    width = max(16, int(width))
    height = max(16, int(height))
    caps = 'capsfilter caps="video/x-raw,width=%d,height=%d,pixel-aspect-ratio=1/1"' % (width, height)

    if scaling == "fit":
        desc = "videoconvert ! videoscale add-borders=true ! %s" % caps
    elif scaling == "stretch":
        desc = "videoconvert ! videoscale add-borders=false ! %s" % caps
    else:
        desc = ("videoconvert ! aspectratiocrop aspect-ratio=%d/%d ! "
                "videoscale add-borders=false ! %s" % (width, height, caps))

    return Gst.parse_bin_from_description(desc, True)


class VideoWidget(Gtk.Bin):
    """
    A Gtk.Bin holding the video sink's widget. Call set_error_callback() to
    learn about unrecoverable playback errors (the caller is expected to fall
    back to something else).
    """

    def __init__(self, uri, width, height, scaling="fill", dim=0.3,
                 audio=False, volume=0.5, use_gl=False,
                 pause_on_battery=False, pause_when_screen_off=True):
        super(VideoWidget, self).__init__()
        init()

        if to_uri(uri) != uri:
            raise ValueError("only local file:// URIs can be played")

        self.uri = uri
        self.dim = max(0.0, min(1.0, dim))
        self.error_callback = None
        self.failed = False
        self.battery = None
        self.dpms = None
        self.dpms_source = 0
        self.manually_paused = False

        self.pipeline = Gst.ElementFactory.make("playbin", None)
        if self.pipeline is None:
            raise RuntimeError("GStreamer 'playbin' element is missing")

        sink, widget = self._make_sink(use_gl)
        self.pipeline.set_property("video-sink", sink)
        self.pipeline.set_property("video-filter", make_filter(scaling, width, height))

        flags = FLAG_VIDEO
        if audio:
            flags |= FLAG_AUDIO | FLAG_SOFT_VOLUME
            self.pipeline.set_property("volume", max(0.0, min(1.0, volume)))
        self.pipeline.set_property("flags", flags)
        self.pipeline.set_property("uri", uri)

        # Gapless looping: queue the same file again right before the end.
        self.pipeline.connect("about-to-finish", self._on_about_to_finish)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        self.bus_handler = bus.connect("message", self._on_bus_message)

        widget.set_hexpand(True)
        widget.set_vexpand(True)
        widget.connect_after("draw", self._on_draw)
        widget.show()
        self.add(widget)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)
        self.connect("destroy", self._on_destroy)

        if pause_on_battery:
            self.battery = _Battery(self._update_state)
        if pause_when_screen_off:
            self.dpms = _Dpms()

    def _make_sink(self, use_gl):
        if use_gl:
            glsink = Gst.ElementFactory.make("gtkglsink", None)
            bin_ = Gst.ElementFactory.make("glsinkbin", None)
            if glsink is not None and bin_ is not None:
                bin_.set_property("sink", glsink)
                glsink.set_property("force-aspect-ratio", False)
                return bin_, glsink.get_property("widget")
            log("GL sink unavailable, falling back to gtksink")

        sink = Gst.ElementFactory.make("gtksink", None)
        if sink is None:
            raise RuntimeError("GStreamer 'gtksink' is missing (install the GStreamer GTK3 plugin)")
        sink.set_property("force-aspect-ratio", False)
        return sink, sink.get_property("widget")

    # -- state ---------------------------------------------------------------

    def play(self):
        self.manually_paused = False
        self._update_state()

    def pause(self):
        self.manually_paused = True
        self._update_state()

    def _should_play(self):
        if self.failed or self.manually_paused or not self.get_mapped():
            return False
        if self.battery is not None and self.battery.on_battery():
            return False
        if self.dpms is not None and self.dpms.screen_off():
            return False
        return True

    def _update_state(self, *args):
        if self.pipeline is None:
            return
        # PLAYING <-> PAUSED is asynchronous and doesn't wait on streaming threads.
        target = Gst.State.PLAYING if self._should_play() else Gst.State.PAUSED
        self.pipeline.set_state(target)

    def _poll_dpms(self):
        self._update_state()
        return GLib.SOURCE_CONTINUE

    def _on_map(self, widget):
        self._update_state()
        if self.dpms is not None and self.dpms.dpy and not self.dpms_source:
            self.dpms_source = GLib.timeout_add_seconds(DPMS_POLL_SECONDS, self._poll_dpms)

    def _on_unmap(self, widget):
        if self.dpms_source:
            GLib.source_remove(self.dpms_source)
            self.dpms_source = 0
        self._update_state()

    def _on_destroy(self, widget):
        self.shutdown()

    def shutdown(self):
        if self.dpms_source:
            GLib.source_remove(self.dpms_source)
            self.dpms_source = 0
        if self.pipeline is not None:
            bus = self.pipeline.get_bus()
            bus.disconnect(self.bus_handler)
            bus.remove_signal_watch()
            _stop_pipeline_async(self.pipeline)
            self.pipeline = None
        if self.battery is not None:
            self.battery.close()
            self.battery = None
        if self.dpms is not None:
            self.dpms.close()
            self.dpms = None

    # -- callbacks -----------------------------------------------------------

    def _on_about_to_finish(self, playbin):
        # Runs on a streaming thread; setting the uri here is allowed.
        playbin.set_property("uri", self.uri)

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            # Fallback loop in case gapless re-queueing didn't happen. A
            # flushing seek waits for the streaming thread, so keep it off the
            # main thread for the same reason as _stop_pipeline_async().
            pipeline = self.pipeline
            threading.Thread(target=pipeline.seek_simple,
                             args=(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0),
                             name="csv-loop", daemon=True).start()
        elif t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            log("playback error: %s (%s)" % (err.message, dbg))
            self.failed = True
            self.shutdown()
            if self.error_callback is not None:
                GLib.idle_add(self.error_callback, self)

    def _on_draw(self, widget, cr):
        if self.dim > 0.0:
            cr.set_source_rgba(0.0, 0.0, 0.0, self.dim)
            cr.paint()
        return False

    def set_error_callback(self, callback):
        self.error_callback = callback


def create_from_settings(width, height, audio_allowed=True):
    """
    Build a VideoWidget from the GSettings configuration. Returns None (and
    logs why) if the feature is disabled, unconfigured or the file unusable.
    """
    settings = config.get_settings()
    if settings is None:
        log("schema %s not installed, using the wallpaper" % config.SCHEMA_ID)
        return None
    if not settings.get_boolean("enabled"):
        log("video disabled in settings, using the wallpaper")
        return None

    configured = settings.get_string("video-uri")
    if not configured:
        log("no video file set, using the wallpaper")
        return None
    uri = to_uri(configured)
    if uri is None:
        log("not a local file, refusing to play %r; using the wallpaper" % configured)
        return None
    if not is_playable_file(uri):
        log("not a readable regular file: %r; using the wallpaper" % uri)
        return None

    return VideoWidget(uri, width, height,
                       scaling=settings.get_string("scaling"),
                       dim=settings.get_double("dim"),
                       audio=audio_allowed and not settings.get_boolean("mute"),
                       volume=settings.get_double("volume"),
                       use_gl=settings.get_boolean("hardware-acceleration"),
                       pause_on_battery=settings.get_boolean("pause-on-battery"),
                       pause_when_screen_off=settings.get_boolean("pause-when-screen-off"))

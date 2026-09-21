"""VideoWidget, URI validation and GStreamer hardening."""

import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gst, GLib
    from cinnamon_screensaver_video import player, config
    Gst.init(None)
    HAVE_GST = True
except (ImportError, ValueError):
    HAVE_GST = False


def has_elements(*names):
    return all(Gst.ElementFactory.find(n) is not None for n in names)


@unittest.skipUnless(HAVE_GST, "PyGObject/GStreamer not available")
class UriTests(unittest.TestCase):

    def test_to_uri(self):
        self.assertEqual(player.to_uri("/tmp/a b.mp4"), "file:///tmp/a%20b.mp4")
        self.assertEqual(player.to_uri("file:///tmp/a.mp4"), "file:///tmp/a.mp4")
        for bad in ("", None, "a.mp4", "http://example.com/a.mp4",
                    "https://example.com/a.mp4", "rtsp://example.com/s", "smb://host/a.mp4"):
            self.assertIsNone(player.to_uri(bad), bad)

    def test_is_playable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "v.mp4")
            open(f, "wb").close()
            link = os.path.join(tmp, "link.mp4")
            os.symlink(f, link)
            self.assertTrue(player.is_playable_file(player.to_uri(f)))
            self.assertTrue(player.is_playable_file(player.to_uri(link)))
            self.assertFalse(player.is_playable_file(player.to_uri(tmp)))
            self.assertFalse(player.is_playable_file(player.to_uri(os.path.join(tmp, "missing.mp4"))))
            if os.geteuid() != 0:
                os.chmod(f, 0)
                self.assertFalse(player.is_playable_file(player.to_uri(f)))
        self.assertFalse(player.is_playable_file("file:///dev/zero"))


@unittest.skipUnless(HAVE_GST, "PyGObject/GStreamer not available")
class SettingsTests(unittest.TestCase):

    def setUp(self):
        self.settings = config.get_settings()
        self.assertIsNotNone(self.settings, "test schema not installed")
        self.settings.set_boolean("enabled", True)

    def tearDown(self):
        self.settings.reset("video-uri")
        self.settings.reset("enabled")

    def check_refused(self, value):
        self.settings.set_string("video-uri", value)
        self.assertIsNone(player.create_from_settings(640, 360))

    def test_refuses_network_uris(self):
        self.check_refused("http://127.0.0.1:9/video.mp4")
        self.check_refused("rtsp://127.0.0.1:9/stream")

    def test_refuses_devices_dirs_and_missing(self):
        self.check_refused("/dev/zero")
        self.check_refused("/")
        self.check_refused("/nonexistent/video.mp4")
        self.check_refused("")

    def test_disabled(self):
        self.settings.set_boolean("enabled", False)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            self.settings.set_string("video-uri", f.name)
            self.assertIsNone(player.create_from_settings(640, 360))


@unittest.skipUnless(HAVE_GST, "PyGObject/GStreamer not available")
class PipelineTests(unittest.TestCase):

    def setUp(self):
        player.init()

    def test_network_elements_disabled(self):
        registry = Gst.Registry.get()
        for name in player.NETWORK_ELEMENTS:
            feature = registry.lookup_feature(name)
            if feature is not None:
                self.assertEqual(feature.get_rank(), Gst.Rank.NONE, name)

    def negotiated(self, scaling, w, h, src_caps):
        pipeline = Gst.Pipeline()
        src = Gst.parse_bin_from_description('videotestsrc num-buffers=2 ! capsfilter caps="%s"' % src_caps, True)
        filt = player.make_filter(scaling, w, h)
        sink = Gst.ElementFactory.make("fakesink", None)
        for e in (src, filt, sink):
            pipeline.add(e)
        src.link(filt)
        filt.link(sink)
        pipeline.set_state(Gst.State.PLAYING)
        msg = pipeline.get_bus().timed_pop_filtered(10 * Gst.SECOND,
                                                    Gst.MessageType.EOS | Gst.MessageType.ERROR)
        caps = filt.get_static_pad("src").get_current_caps()
        pipeline.set_state(Gst.State.NULL)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.type, Gst.MessageType.EOS)
        s = caps.get_structure(0)
        return s.get_value("width"), s.get_value("height")

    @unittest.skipUnless(HAVE_GST and has_elements("videotestsrc", "aspectratiocrop", "videoscale"),
                         "GStreamer base/good plugins missing")
    def test_filter_outputs_target_size(self):
        for mode in ("fill", "fit", "stretch"):
            self.assertEqual(self.negotiated(mode, 800, 800, "video/x-raw,width=320,height=180"),
                             (800, 800), mode)

    @unittest.skipUnless(HAVE_GST and has_elements("playbin", "fakesink", "typefind"),
                         "GStreamer playbin missing")
    def test_playlist_disguised_as_video_does_not_touch_network(self):
        # An HLS master playlist saved with a video extension. With adaptive
        # demuxers disabled nothing may be autoplugged that follows the URL.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "video.mp4")
            with open(path, "w") as f:
                f.write("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nhttp://127.0.0.1:9/stream.m3u8\n")
            playbin = Gst.ElementFactory.make("playbin", None)
            playbin.set_property("video-sink", Gst.ElementFactory.make("fakesink", None))
            playbin.set_property("audio-sink", Gst.ElementFactory.make("fakesink", None))
            playbin.set_property("uri", player.to_uri(path))
            created = []
            playbin.connect("element-setup", lambda pb, e: created.append(e.get_factory().get_name()
                                                                          if e.get_factory() else ""))
            playbin.set_state(Gst.State.PAUSED)
            msg = playbin.get_bus().timed_pop_filtered(10 * Gst.SECOND,
                                                       Gst.MessageType.ERROR | Gst.MessageType.ASYNC_DONE)
            playbin.set_state(Gst.State.NULL)
            self.assertIsNotNone(msg)
            self.assertEqual(msg.type, Gst.MessageType.ERROR)
            self.assertFalse(set(created) & set(player.NETWORK_ELEMENTS), created)


def make_clip(path):
    # VP8/WebM only needs gst-plugins-good.
    subprocess.run(["gst-launch-1.0", "-q", "videotestsrc", "num-buffers=45", "!",
                    "video/x-raw,width=320,height=180,framerate=30/1", "!",
                    "vp8enc", "deadline=1", "!", "webmmux", "!", "filesink", "location=" + path],
                   check=True, timeout=60)


@unittest.skipUnless(HAVE_GST and os.environ.get("DISPLAY") and shutil.which("gst-launch-1.0"),
                     "needs a display (run under xvfb-run) and gst-launch-1.0")
class WidgetTests(unittest.TestCase):

    def setUp(self):
        from gi.repository import Gtk
        if not Gtk.init_check(None)[0]:
            self.skipTest("Gtk can't open the display")
        if not has_elements("gtksink", "vp8enc", "webmmux", "vp8dec"):
            self.skipTest("gtksink or VP8 elements missing")
        self.Gtk = Gtk
        self.tmp = tempfile.mkdtemp()
        self.clip = os.path.join(self.tmp, "clip.webm")
        make_clip(self.clip)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_widget(self, uri, seconds):
        Gtk = self.Gtk
        video = player.VideoWidget(uri, 320, 180, pause_when_screen_off=False)
        errors = []
        video.set_error_callback(lambda v: errors.append(v))
        win = Gtk.Window()
        win.add(video)
        win.show_all()
        positions = []

        def sample():
            if video.pipeline is not None:
                ok, pos = video.pipeline.query_position(Gst.Format.TIME)
                positions.append(pos / Gst.SECOND if ok else None)
            return True

        GLib.timeout_add(250, sample)
        GLib.timeout_add(int(seconds * 1000), Gtk.main_quit)
        Gtk.main()
        win.destroy()
        return positions, errors

    def test_plays_and_loops(self):
        positions, errors = self.run_widget(player.to_uri(self.clip), 3.5)
        self.assertEqual(errors, [])
        valid = [p for p in positions if p is not None]
        self.assertTrue(valid, positions)
        # The 1.5 s clip must wrap around at least once in 3.5 s.
        self.assertTrue(any(b < a for a, b in zip(valid, valid[1:])), valid)

    def test_error_reported_for_corrupt_file(self):
        bad = os.path.join(self.tmp, "bad.mp4")
        with open(bad, "wb") as f:
            f.write(os.urandom(20000))
        positions, errors = self.run_widget(player.to_uri(bad), 2)
        self.assertEqual(len(errors), 1)

    def test_shutdown_does_not_block_main_thread(self):
        video = player.VideoWidget(player.to_uri(self.clip), 320, 180, pause_when_screen_off=False)
        win = self.Gtk.Window()
        win.add(video)
        win.show_all()
        GLib.timeout_add(700, self.Gtk.main_quit)
        self.Gtk.main()
        start = time.monotonic()
        win.destroy()
        self.assertLess(time.monotonic() - start, 0.5)
        deadline = time.monotonic() + 5
        while any(t.name == "csv-stop" for t in threading.enumerate()) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(any(t.name == "csv-stop" for t in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()

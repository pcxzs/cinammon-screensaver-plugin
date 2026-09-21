"""
The "Video" tab added to Cinnamon's Screensaver page in System Settings.
Only imported inside cinnamon-settings, where xapp's settings widgets exist.
"""

import builtins
import shutil
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from xapp.GSettingsWidgets import (GSettingsSwitch, GSettingsFileChooser, GSettingsComboBox,
                                   GSettingsRange, SettingsPage, SettingsWidget)

from cinnamon_screensaver_video import config

SCHEMA = config.SCHEMA_ID
PREVIEW_COMMAND = "cinnamon-screensaver-video-preview"
PAGE_NAME = "video"


def _(s):
    # cinnamon-settings installs a gettext "_" builtin; fall back to English.
    translate = getattr(builtins, "_", None)
    return translate(s) if translate else s


def _on_preview_clicked(button):
    command = shutil.which(PREVIEW_COMMAND)
    if command is None:
        print("%s not found" % PREVIEW_COMMAND)
        return
    try:
        subprocess.Popen([command], stdin=subprocess.DEVNULL)
    except OSError as e:
        print("Could not start %s: %s" % (PREVIEW_COMMAND, e))


def build_page():
    page = SettingsPage()

    section = page.add_section(_("Video background"))
    size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)

    widget = GSettingsSwitch(_("Play a video on the screensaver and lock screen"), SCHEMA, "enabled")
    widget.set_tooltip_text(_("Replaces the wallpaper behind the clock and unlock dialog"))
    section.add_row(widget)

    chooser = GSettingsFileChooser(_("Video file"), SCHEMA, "video-uri", size_group=size_group)
    video_filter = Gtk.FileFilter()
    video_filter.set_name(_("Videos"))
    video_filter.add_mime_type("video/*")
    chooser.content_widget.add_filter(video_filter)
    all_filter = Gtk.FileFilter()
    all_filter.set_name(_("All files"))
    all_filter.add_pattern("*")
    chooser.content_widget.add_filter(all_filter)
    section.add_reveal_row(chooser, SCHEMA, "enabled")

    scaling = [("fill", _("Fill (crop to cover the screen)")),
               ("fit", _("Fit (keep whole video, add borders)")),
               ("stretch", _("Stretch"))]
    section.add_reveal_row(GSettingsComboBox(_("Scaling"), SCHEMA, "scaling", scaling,
                                             valtype=str, size_group=size_group),
                           SCHEMA, "enabled")

    section.add_reveal_row(GSettingsRange(_("Darken"), SCHEMA, "dim",
                                          _("None"), _("Black"), 0.0, 1.0, 0.05, show_value=False),
                           SCHEMA, "enabled")

    widget = SettingsWidget()
    button = Gtk.Button(label=_("Preview"))
    button.set_tooltip_text(_("Play the video full screen with the current settings. Press Esc to close."))
    button.connect("clicked", _on_preview_clicked)
    widget.pack_end(button, False, False, 0)
    section.add_reveal_row(widget, SCHEMA, "enabled")

    section = page.add_section(_("Sound"))
    section.add_row(GSettingsSwitch(_("Mute"), SCHEMA, "mute"))
    widget = GSettingsRange(_("Volume"), SCHEMA, "volume", _("Quiet"), _("Loud"),
                            0.0, 1.0, 0.05, show_value=False)
    widget.set_tooltip_text(_("Sound is played on the primary monitor only"))
    section.add_reveal_row(widget, SCHEMA, "mute", [False])

    section = page.add_section(_("Performance"))
    section.add_row(GSettingsSwitch(_("Pause while the monitors are powered off"), SCHEMA, "pause-when-screen-off"))
    section.add_row(GSettingsSwitch(_("Show a still frame while on battery"), SCHEMA, "pause-on-battery"))
    widget = GSettingsSwitch(_("Use OpenGL rendering"), SCHEMA, "hardware-acceleration")
    widget.set_tooltip_text(_("Can reduce CPU usage on high resolution monitors. Turn off if the lock screen shows a black background."))
    section.add_row(widget)

    label = Gtk.Label()
    label.set_markup("<small>%s</small>" % _("Changes take effect the next time the screensaver starts."))
    label.set_margin_top(6)
    page.pack_start(label, False, False, 0)

    return page

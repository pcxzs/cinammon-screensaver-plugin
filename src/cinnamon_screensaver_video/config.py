"""GSettings access for cinnamon-screensaver-video."""

from gi.repository import Gio

SCHEMA_ID = "org.cinnamon.screensaver-video"


def get_settings():
    """
    Return the Gio.Settings object, or None if the schema isn't installed.

    Gio.Settings.new() aborts the whole process on a missing schema, which
    must never happen inside the screensaver or System Settings.
    """
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(SCHEMA_ID, True) is None:
        return None
    return Gio.Settings.new(SCHEMA_ID)

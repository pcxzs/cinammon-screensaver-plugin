"""All places that carry the version number agree with debian/changelog."""

import os
import re
import unittest

from tests import ROOT


def changelog_version():
    with open(os.path.join(ROOT, "debian", "changelog")) as f:
        return re.match(r"\S+ \(([^)]+)\)", f.readline()).group(1)


class VersionTests(unittest.TestCase):

    def test_package_version(self):
        import cinnamon_screensaver_video
        upstream = changelog_version().split("-")[0].split("~")[0]
        self.assertEqual(cinnamon_screensaver_video.__version__, upstream)

    def test_man_page_version(self):
        with open(os.path.join(ROOT, "data", "cinnamon-screensaver-video-preview.1")) as f:
            header = f.readline()
        upstream = changelog_version().split("-")[0].split("~")[0]
        self.assertIn("cinnamon-screensaver-video %s" % upstream, header)

    def test_changelog_md_mentions_version(self):
        upstream = changelog_version().split("-")[0].split("~")[0]
        with open(os.path.join(ROOT, "CHANGELOG.md")) as f:
            self.assertIn("## %s" % upstream, f.read())


if __name__ == "__main__":
    unittest.main()

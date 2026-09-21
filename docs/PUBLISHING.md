# Publishing guide

How to release cinnamon-screensaver-video on GitHub, as Debian/Ubuntu
packages (PPA, official Debian, your own apt repository), for other
distributions, and how to propose the feature to Cinnamon upstream.

---

## 0. Before the first publication

### Replace the placeholders

| Placeholder | Files | Replace with |
|---|---|---|
| `OWNER` | `debian/control`, `debian/copyright` | your GitHub user or organisation |
| `Your Name <your-email@example.com>` | `debian/control`, `debian/changelog` | the maintainer name and e-mail shown in the package |

```sh
grep -rn -e OWNER -e "your-email@example.com" --exclude-dir=.git .
```

To keep your personal e-mail out of the public package and git history, use a
dedicated address. For commits, GitHub's no-reply address works:
*Settings → Emails → Keep my email address private* shows it as
`<id>+<user>@users.noreply.github.com`.

```sh
git config user.name  "Your Name"
git config user.email "<id>+<user>@users.noreply.github.com"
```

The initial commit in this repository uses a neutral placeholder author. Take
it over with your identity:

```sh
git commit --amend --reset-author --no-edit
```

For Debian packaging, the tools read `DEBFULLNAME` and `DEBEMAIL`:

```sh
export DEBFULLNAME="Your Name" DEBEMAIL="packages@your-domain.example"
```

### Decide on the GSettings schema id

The schema is `org.cinnamon.screensaver-video`. That's fine for a third-party
add-on, but the `org.cinnamon.*` namespace belongs to the Cinnamon project. If
Linux Mint objects, or before an official Debian upload, consider renaming it
(e.g. `io.github.OWNER.CinnamonScreensaverVideo`). It's used in
`data/*.gschema.xml`, `src/cinnamon_screensaver_video/config.py`, the man page,
the README and `debian/tests/smoke`. Renaming later means users have to pick
their video again.

### Release checklist (every version)

1. Update `CHANGELOG.md`.
2. `dch -v X.Y.Z "..."`, then `dch -r` to finalise `debian/changelog`.
3. Set `__version__` in `src/cinnamon_screensaver_video/__init__.py` and the
   version in `data/cinnamon-screensaver-video-preview.1`.
   `make test` fails if these disagree with `debian/changelog`.
4. `xvfb-run make test`, then `make deb`, then `lintian dist/*.deb`.
5. Install the `.deb` locally and do a real lock/unlock and monitor power-off test.
6. Commit, then tag with `git tag -s vX.Y.Z` (or `-a`), then `git push --follow-tags`.

---

## 1. GitHub

1. Create an **empty** repository named `cinnamon-screensaver-video` on GitHub,
   without a README or license.
2. Push:
   ```sh
   git remote add origin git@github.com:OWNER/cinnamon-screensaver-video.git
   git push -u origin main
   ```
3. Repository settings:
   - **Security → Private vulnerability reporting: enable.** `SECURITY.md` points there.
   - Add a description and topics: `cinnamon`, `linux-mint`, `screensaver`,
     `lock-screen`, `gstreamer`, `video-wallpaper`.
   - Optionally, add branch protection on `main` that requires the CI check.
4. The **CI** workflow (`.github/workflows/ci.yml`) runs lint, the tests
   (playback tests under Xvfb), the Debian build, lintian and an install smoke
   test on every push and pull request.
5. **Release:** push a tag `vX.Y.Z` that matches `debian/changelog`. The
   **Release** workflow builds the `.deb` plus `SHA256SUMS` and creates a
   **draft** release. Review it on the *Releases* page and click *Publish*.

---

## 2. Ubuntu and Linux Mint: Launchpad PPA (recommended first step)

A PPA gives Ubuntu and Mint users `apt install` and automatic updates. Linux
Mint 22.x is based on Ubuntu 24.04 (`noble`), and Mint 21.x on 22.04 (`jammy`).

One-time setup:

1. Create a Launchpad account at <https://launchpad.net>.
2. Create an OpenPGP key and upload it:
   ```sh
   gpg --full-generate-key                # RSA 4096 or ed25519
   gpg --keyserver keyserver.ubuntu.com --send-keys <KEYID>
   ```
   Import it on Launchpad (*Your profile → OpenPGP keys*) and confirm the
   e-mail Launchpad sends you.
3. Sign the *Ubuntu Code of Conduct* on Launchpad.
4. Create a PPA: *Your profile → Create a new PPA*, named e.g. `cinnamon-screensaver-video`.
5. Install the tools: `sudo apt install devscripts dput debhelper dh-python`.

Upload for each Ubuntu series, starting with `noble`:

```sh
# Versions must be unique per upload and sort below a future official package.
dch -v 0.9.0~ppa1~noble1 -D noble "PPA build for noble."
debuild -S -sa -k<KEYID>                 # builds and signs a *source* package
dput ppa:<launchpad-user>/cinnamon-screensaver-video ../cinnamon-screensaver-video_0.9.0~ppa1~noble1_source.changes
git checkout debian/changelog            # don't commit the PPA-specific entry
```

Launchpad builds the binary itself and e-mails you the result. Repeat with
`jammy` (`~jammy1`) if you want to support Mint 21. Before uploading for an
older release, check that it has the dependencies (`gstreamer1.0-gtk3` and the
rest).

Users then run:

```sh
sudo add-apt-repository ppa:<launchpad-user>/cinnamon-screensaver-video
sudo apt install cinnamon-screensaver-video
```

The source format is `3.0 (native)`, which Launchpad accepts. If you later go
for official Debian (below), switch to `3.0 (quilt)` first and use
`0.9.0-0ubuntu1~ppa1`-style versions.

---

## 3. Official Debian (and from there, Ubuntu)

This takes longer, because every upload needs a Debian Developer to sponsor
it. It's worth it once the project has users.

1. **Convert to a non-native package.** Upstream releases become tarballs and
   the Debian packaging is versioned separately:
   ```sh
   echo "3.0 (quilt)" > debian/source/format
   dch -v 0.9.0-1 "Initial release. (Closes: #<ITP bug number>)"
   # upstream tarball, generated from the git tag:
   git archive --prefix=cinnamon-screensaver-video-0.9.0/ -o ../cinnamon-screensaver-video_0.9.0.orig.tar.gz v0.9.0
   ```
   Add a `debian/watch` file that tracks GitHub tags, and
   `debian/upstream/metadata`. Debian prefers `debian/` to be excluded from
   the upstream tarball; you can keep it in a separate packaging branch or
   repository.
2. **File an ITP** ("Intent To Package") bug: `reportbug wnpp`, choose ITP,
   and describe the package.
3. **Build cleanly** in a minimal chroot: `sbuild` or `pbuilder`, plus
   `lintian -I --pedantic`.
4. **Upload to mentors.debian.net**, then file an **RFS** ("Request For
   Sponsorship") bug against the `sponsorship-requests` pseudo-package. Also
   ask the **Debian Cinnamon Team** (<https://salsa.debian.org/cinnamon-team>,
   mailing list `debian-cinnamon@lists.debian.org`), who maintain Cinnamon in
   Debian and are the natural sponsors or co-maintainers.
5. Expect reviewers to ask about the **`.pth` start-up hook**: it runs code in
   every Python process. Point them to `SECURITY.md` and the tests. Their
   preferred long-term answer is upstream support (section 6), which is
   another reason to pursue that.

Packages accepted into Debian unstable reach Ubuntu automatically in its next
release, and from there Linux Mint.

---

## 4. Your own apt repository (optional)

If you don't want to use Launchpad, you can host a signed apt repository on
GitHub Pages or any static web host:

```sh
sudo apt install reprepro
# conf/distributions: Codename: stable / Components: main / Architectures: all / SignWith: <KEYID>
reprepro -b repo includedeb stable dist/cinnamon-screensaver-video_0.9.0_all.deb
```

Publish `repo/` and your public key, and document the setup with a
`signed-by=` keyring in `/etc/apt/sources.list.d/`. This is more work to
maintain than a PPA; only do it if you need to.

---

## 5. Other distributions

`make install` works everywhere. The package-name differences are in the
dependencies:

| Distribution | Where to publish | Notes |
|---|---|---|
| Arch / Manjaro | **AUR**: a `PKGBUILD` running `make DESTDIR="$pkgdir" PYTHONDIR=$(python -c 'import sysconfig;print(sysconfig.get_path("purelib"))') install` | depends: `cinnamon-screensaver python-gobject gst-plugins-base gst-plugins-good gst-plugin-gtk`; optdepends: `gst-libav` |
| Fedora | **COPR** (a free build service, like a PPA) with an RPM `.spec` | depends: `cinnamon-screensaver python3-gobject gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-good-gtk` |
| openSUSE / many at once | **Open Build Service** (build.opensuse.org) | can build Debian, Ubuntu, Fedora and openSUSE packages from one project |

On RPM distributions, run `glib-compile-schemas` in `%posttrans` (or rely on
the distribution's file triggers).

---

## 6. Cinnamon Spices — not applicable

The Cinnamon Spices site (cinnamon-spices.linuxmint.com) only hosts
**applets, desklets, extensions and themes**. Those run inside the Cinnamon
shell (JavaScript) or style it. This project runs inside the separate
cinnamon-screensaver process, which Spices can't reach. So it can't be
published there, and a Spices submission would be rejected.

To reach Cinnamon users anyway, announce releases on the Linux Mint forums
(*Software & Applications*, or *Chat about Linux Mint*), on r/linuxmint, and
in Cinnamon's GitHub discussions.

---

## 7. Proposing it to Cinnamon upstream (Linux Mint)

The best long-term home is native support in Cinnamon itself. Then no import
hook is needed at all. The feature spans three Linux Mint repositories:

| Repository | Change |
|---|---|
| `linuxmint/cinnamon-desktop` | new keys in the `org.cinnamon.desktop.screensaver` schema (e.g. `background-video-enabled`, `background-video-uri`, `background-video-scaling`, `background-video-dim`, `background-video-mute`) |
| `linuxmint/cinnamon-screensaver` | `monitorView.py`: play the video in `WallpaperStack` instead of the wallpaper image (port `player.py`, without the hook and watchdog), plus a dependency on the GStreamer GTK sink |
| `linuxmint/cinnamon` | `files/usr/share/cinnamon/cinnamon-settings/modules/cs_screensaver.py`: the Video tab (port `settings_page.py`) |

Suggested approach:

1. **Open a feature-request issue first** on
   `github.com/linuxmint/cinnamon-screensaver`. Link this project, include a
   short screen recording, and explain the security design (local files only,
   no network elements, nothing blocking the main thread). Linux Mint's
   developers decide which features to take; ask whether they'd accept it
   before investing in PRs.
2. If they're interested, send **three small PRs** (schema first, then
   screensaver, then settings), each referencing the others. Follow each
   repository's code style, and keep the video feature off by default.
3. Mention that this package would then be retired, or would only serve
   older Cinnamon versions.

Porting notes: in upstream code, drop `hook.py`, the `.pth` file and the
watchdog (those only exist because this is an add-on). Keep the rest:
URI/file validation, disabling the network-capable elements, the asynchronous
pipeline shutdown, the DPMS pause and the wallpaper fallback.

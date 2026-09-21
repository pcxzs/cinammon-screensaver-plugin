NAME    = cinnamon-screensaver-video

PREFIX  ?= /usr
DESTDIR ?=
# Directory for the .pth hook and the Python package. It must be a
# site-packages directory that the *system* python3 scans for .pth files.
#   Debian/Ubuntu/Mint: /usr/lib/python3/dist-packages   (auto-detected)
#   Others:             python3 -c "import sysconfig; print(sysconfig.get_path('purelib'))"
PYTHONDIR ?= $(shell if [ -d /usr/lib/python3/dist-packages ]; then echo /usr/lib/python3/dist-packages; \
             else python3 -c "import sysconfig; print(sysconfig.get_path('purelib', vars={'base': '$(PREFIX)'}))"; fi)
SCHEMADIR = $(PREFIX)/share/glib-2.0/schemas
PKG       = cinnamon_screensaver_video
MODULES   = __init__ config hook log player settings_page watchdog

.PHONY: all install uninstall test lint deb clean

all:
	@echo "Targets: install, uninstall, test, lint, deb, clean"

install:
	install -d $(DESTDIR)$(PYTHONDIR)/$(PKG)
	for m in $(MODULES); do \
	  install -m644 src/$(PKG)/$$m.py $(DESTDIR)$(PYTHONDIR)/$(PKG)/$$m.py || exit 1; \
	done
	install -Dm644 src/$(PKG).pth $(DESTDIR)$(PYTHONDIR)/$(PKG).pth
	install -Dm644 data/org.cinnamon.screensaver-video.gschema.xml \
	  $(DESTDIR)$(SCHEMADIR)/org.cinnamon.screensaver-video.gschema.xml
	install -Dm755 bin/$(NAME)-preview $(DESTDIR)$(PREFIX)/bin/$(NAME)-preview
	install -Dm644 data/$(NAME)-preview.1 $(DESTDIR)$(PREFIX)/share/man/man1/$(NAME)-preview.1
	@if [ -z "$(DESTDIR)" ]; then glib-compile-schemas $(SCHEMADIR); \
	  echo "Installed. Restart the screensaver once: cinnamon-screensaver-command --exit"; fi

uninstall:
	rm -f  $(DESTDIR)$(PYTHONDIR)/$(PKG).pth
	rm -rf $(DESTDIR)$(PYTHONDIR)/$(PKG)
	rm -f  $(DESTDIR)$(SCHEMADIR)/org.cinnamon.screensaver-video.gschema.xml
	rm -f  $(DESTDIR)$(PREFIX)/bin/$(NAME)-preview
	rm -f  $(DESTDIR)$(PREFIX)/share/man/man1/$(NAME)-preview.1
	@if [ -z "$(DESTDIR)" ]; then glib-compile-schemas $(SCHEMADIR); fi

# Unit tests. "-S" keeps an installed copy of the hook (loaded through the
# .pth file) from shadowing the source tree; tests/__init__.py re-adds the
# system dist-packages directories for PyGObject.
test:
	python3 -S -m unittest discover -s tests -t . -v

lint:
	python3 -m pyflakes src bin/$(NAME)-preview tests
	glib-compile-schemas --strict --dry-run data

# Binary .deb. Uses the Debian source package in debian/ when debhelper is
# available, otherwise a plain dpkg-deb build (packaging/build-deb.sh).
deb:
	@if command -v dh >/dev/null 2>&1; then \
	  dpkg-buildpackage -us -uc -b && mkdir -p dist && mv ../$(NAME)_*_all.deb dist/; \
	else \
	  ./packaging/build-deb.sh; \
	fi

clean:
	rm -rf build dist debian/$(NAME) debian/.debhelper debian/files \
	  debian/*.substvars debian/*.debhelper.log debian/debhelper-build-stamp
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

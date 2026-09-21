#!/bin/sh
# Builds dist/<name>_<version>_all.deb with plain dpkg-deb, for machines
# without debhelper. Package metadata comes from debian/control and
# debian/changelog so there is a single source of truth; the proper Debian
# build is `dpkg-buildpackage -us -uc -b` (see docs/PUBLISHING.md).
set -eu

cd "$(dirname "$0")/.."
NAME=$(dpkg-parsechangelog -S Source)
VERSION=$(dpkg-parsechangelog -S Version)
ROOT="build/deb"

rm -rf "$ROOT"
make --no-print-directory install DESTDIR="$PWD/$ROOT" PREFIX=/usr \
  PYTHONDIR=/usr/lib/python3/dist-packages >/dev/null

gzip -9n "$ROOT/usr/share/man/man1/$NAME-preview.1"

DOC="$ROOT/usr/share/doc/$NAME"
install -Dm644 README.md "$DOC/README.md"
install -Dm644 debian/copyright "$DOC/copyright"
gzip -9n -c debian/changelog > "$DOC/changelog.gz"
chmod 644 "$DOC/changelog.gz"

mkdir -p "$ROOT/DEBIAN" dist
SIZE=$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)

# Binary control file: the binary stanza of debian/control, with the
# Maintainer taken from the source stanza, ${...} substitution variables
# dropped and Version/Installed-Size added.
python3 - "$VERSION" "$SIZE" > "$ROOT/DEBIAN/control" <<'EOF'
import re, sys
version, size = sys.argv[1], sys.argv[2]
stanzas = [s for s in open("debian/control").read().split("\n\n") if s.strip()]

def fields(stanza):
    out, key = [], None
    for line in stanza.splitlines():
        if line.startswith((" ", "\t")) and key:
            out[-1][1].append(line)
        else:
            key, _, value = line.partition(":")
            out.append((key, [value.strip()]))
    return out

source = dict(fields(stanzas[0]))
binary = fields(stanzas[1])
keep = ("Package", "Architecture", "Depends", "Recommends", "Suggests",
        "Enhances", "Section", "Priority", "Description")
out = {}
for key, value in binary:
    if key not in keep:
        continue
    if key in ("Depends", "Recommends", "Suggests", "Enhances"):
        items = [i.strip() for i in " ".join(value).split(",")]
        items = [i for i in items if i and not re.match(r"\$\{.*\}$", i)]
        if key == "Depends":
            items.insert(0, "python3")
        out[key] = [", ".join(items)]
    else:
        out[key] = value
out.setdefault("Section", source.get("Section", ["misc"]))
out.setdefault("Priority", source.get("Priority", ["optional"]))

order = ("Package", "Version", "Architecture", "Maintainer", "Installed-Size",
         "Depends", "Recommends", "Suggests", "Enhances", "Section", "Priority",
         "Homepage", "Description")
out["Version"] = [version]
out["Maintainer"] = source["Maintainer"]
out["Installed-Size"] = [size]
if "Homepage" in source:
    out["Homepage"] = source["Homepage"]
for key in order:
    if key in out:
        value = out[key]
        print("%s: %s" % (key, value[0]))
        for line in value[1:]:
            print(line)
EOF

find "$ROOT" -type d -exec chmod 755 {} +
dpkg-deb --root-owner-group --build "$ROOT" "dist/${NAME}_${VERSION}_all.deb"

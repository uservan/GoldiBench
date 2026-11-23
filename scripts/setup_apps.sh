#!/usr/bin/env bash
# RawTherapee 5.13, GIMP 3.2.6, Inkscape 1.4.4 and Blender 4.5.15 LTS for the multi-app bench (scripts/bench/ops_<app>.py), set up like
# setup_darktable.sh: x86_64 AppImages (+ release sources, for parameter names and defaults) cached on /shared with their
# sha256, extracted onto node-local NVMe. Idempotent.
set -euo pipefail
DATA=${VE_DATA:-${GOLDIBENCH_DATA:-$(cd "$(dirname "$0")/.." && pwd)/data}}
LOCAL=${VE_LOCAL:-$HOME/.cache/goldibench}
APPS=$LOCAL/apps
ROOT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$APPS"

# fetch <cache dir> <url>...: download once, record sha256 on first download, verify every time
fetch(){
  local cache=$1;shift;mkdir -p "$cache"
  for u in "$@"; do local f=$cache/$(basename "$u")
    [ -f "$f" ] || { curl -fL --retry 5 --retry-all-errors -o "$f.part" "$u" && mv "$f.part" "$f"; } \
      || { echo "download failed: $u" >&2; rm -f "$f.part"; return 1; }
  done
  (cd "$cache" && { [ -f SHA256SUMS ] || sha256sum $(for u in "$@"; do basename "$u"; done) > SHA256SUMS; } && sha256sum -c --quiet SHA256SUMS)
  # the paper's binaries: every file must match env/apps.sha256 (a truncated or changed download fails here)
  (cd "$(dirname "$cache")" && grep "  $(basename "$cache")/" "$ROOT/env/apps.sha256" | sha256sum -c --quiet -) \
    || { echo "sha256 differs from env/apps.sha256 in $cache: delete the file(s) and rerun, or place the paper's copy there" >&2; return 1; }
}
# extract <AppImage> <dest>
extract(){
  [ -d "$2/squashfs-root" ] && return
  rm -rf "$2";mkdir -p "$2";cp "$1" "$2/";(cd "$2" && chmod +x "$(basename "$1")" && "./$(basename "$1")" --appimage-extract > /dev/null)
}

RT=5.13 RTURL=https://github.com/RawTherapee/RawTherapee/releases/download/5.13
fetch "$DATA/apps/rawtherapee-$RT" "$RTURL/RawTherapee_${RT}_x86_64_release.AppImage" "$RTURL/rawtherapee-$RT.tar.xz"
extract "$DATA/apps/rawtherapee-$RT/RawTherapee_${RT}_x86_64_release.AppImage" "$APPS/rawtherapee-$RT"
[ -d "$APPS/rawtherapee-src/rtengine" ] || { rm -rf "$APPS/rawtherapee-src";mkdir -p "$APPS/rawtherapee-src"
  tar -xJf "$DATA/apps/rawtherapee-$RT/rawtherapee-$RT.tar.xz" -C "$APPS/rawtherapee-src" --strip-components=1; }

G=3.2.6 GURL=https://download.gimp.org/gimp/v3.2
fetch "$DATA/apps/gimp-$G" "$GURL/linux/GIMP-$G-x86_64.AppImage" "$GURL/gimp-$G.tar.xz"
extract "$DATA/apps/gimp-$G/GIMP-$G-x86_64.AppImage" "$APPS/gimp-$G"
# AppRun execs the GUI binary; AppRun-console is the same environment for gimp-console (headless batch renders)
GR=$APPS/gimp-$G/squashfs-root
[ -x "$GR/AppRun-console" ] || { sed 's#usr/bin/org.gimp.GIMP.Stable#usr/bin/gimp-console-3.2#' "$GR/AppRun" > "$GR/AppRun-console";chmod +x "$GR/AppRun-console"; }
[ -d "$APPS/gimp-src/app" ] || { rm -rf "$APPS/gimp-src";mkdir -p "$APPS/gimp-src"
  tar -xJf "$DATA/apps/gimp-$G/gimp-$G.tar.xz" -C "$APPS/gimp-src" --strip-components=1; }

I=1.4.4
# inkscape.org has at times served only the first 19,922,944 bytes of the AppImage (2026-11-22 / 11-23); the download then
# fails. Put a copy with the sha256 of env/apps.sha256 into $DATA/apps/inkscape-$I/ and rerun.
fetch "$DATA/apps/inkscape-$I" https://inkscape.org/gallery/item/59506/Inkscape-$I.AppImage https://inkscape.org/gallery/item/59505/inkscape-$I.tar.xz
extract "$DATA/apps/inkscape-$I/Inkscape-$I.AppImage" "$APPS/inkscape-$I"

B=4.5.15
fetch "$DATA/apps/blender-$B" "https://download.blender.org/release/Blender4.5/blender-$B-linux-x64.tar.xz"
[ -x "$APPS/blender-$B/blender" ] || { rm -rf "$APPS/blender-$B";mkdir -p "$APPS/blender-$B"
  tar -xJf "$DATA/apps/blender-$B/blender-$B-linux-x64.tar.xz" -C "$APPS/blender-$B" --strip-components=1; }

ls "$APPS/rawtherapee-$RT/squashfs-root/usr/bin/" | grep -i rawtherapee
"$APPS/inkscape-$I/squashfs-root/AppRun" --version
"$APPS/blender-$B/blender" --version | head -1
ls "$APPS/gimp-$G/squashfs-root/usr/bin/" | grep -i gimp | head

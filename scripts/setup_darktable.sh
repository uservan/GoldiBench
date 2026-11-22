#!/usr/bin/env bash
# darktable 5.6.2 for the bench pilot (scripts/bench/dt_params.py): the x86_64 AppImage, extracted (darktable-cli), and the
# release source tree (its src/iop headers give the module params structs). Downloads are cached on /shared with their
# sha256 so a node restart needs no network; the extracted copies live on node-local NVMe. Idempotent.
set -euo pipefail
DATA=${VE_DATA:-${GOLDIBENCH_DATA:-$(cd "$(dirname "$0")/.." && pwd)/data}}
LOCAL=${VE_LOCAL:-$HOME/.cache/goldibench}
V=5.6.2 URL=https://github.com/darktable-org/darktable/releases/download/release-5.6.2
CACHE=$DATA/apps/darktable-$V APPS=$LOCAL/apps
mkdir -p "$CACHE" "$APPS"
for f in Darktable-$V-x86_64.AppImage darktable-$V.tar.xz; do
  [ -f "$CACHE/$f" ] || { curl -fL --retry 5 --retry-all-errors -o "$CACHE/$f.part" "$URL/$f" && mv "$CACHE/$f.part" "$CACHE/$f"; } \
    || { echo "download failed: $URL/$f" >&2; rm -f "$CACHE/$f.part"; exit 1; }
done
(cd "$CACHE" && { [ -f SHA256SUMS ] || sha256sum Darktable-$V-x86_64.AppImage darktable-$V.tar.xz > SHA256SUMS; } && sha256sum -c --quiet SHA256SUMS)
if [ ! -x "$APPS/darktable-$V/squashfs-root/usr/bin/darktable-cli" ]; then
  rm -rf "$APPS/darktable-$V"; mkdir -p "$APPS/darktable-$V"; cp "$CACHE/Darktable-$V-x86_64.AppImage" "$APPS/darktable-$V/"
  (cd "$APPS/darktable-$V" && chmod +x Darktable-$V-x86_64.AppImage && ./Darktable-$V-x86_64.AppImage --appimage-extract > /dev/null)
fi
if [ ! -d "$APPS/darktable-src/src/iop" ]; then
  rm -rf "$APPS/darktable-src"; mkdir -p "$APPS/darktable-src"
  tar -xJf "$CACHE/darktable-$V.tar.xz" -C "$APPS/darktable-src" --strip-components=1
fi
"$APPS/darktable-$V/squashfs-root/usr/bin/darktable-cli" --version | head -1

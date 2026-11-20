#!/usr/bin/env bash
# Xvfb, xdotool, openbox and x11-utils for the GUI benches without root (nodes where `sudo apt-get install` is not
# possible): the Ubuntu 24.04 packages are downloaded with `apt-get download` and unpacked with `dpkg -x` under
# $VE_LOCAL/xroot. Use them with `source scripts/xtools_env.sh` (PATH / LD_LIBRARY_PATH).
# Xvfb runs xkbcomp from its compiled-in directory /usr/bin (no command-line option changes it): the unpacked copy
# has that one string patched to /tmp/xkb (same length), where a wrapper runs the unpacked xkbcomp. Idempotent.
set -euo pipefail
LOCAL=${VE_LOCAL:-$HOME/.cache/goldibench}
R=$LOCAL/xroot DEBS=$LOCAL/xroot-debs
PKGS="xvfb xdotool openbox x11-utils xkb-data x11-xkb-utils libxdo3 libxfont2 libxkbfile1 libfontenc1 libobrender32v5 libobt2v5
      libstartup-notification0 libpangoxft-1.0-0 libimlib2t64 libxcb-util1"
if [ ! -f "$R/.ready" ]; then
  mkdir -p "$DEBS" "$R"
  (cd "$DEBS" && apt-get download $PKGS > /dev/null)
  for d in "$DEBS"/*.deb; do dpkg -x "$d" "$R"; done
  [ "$(grep -c -a /usr/bin "$R/usr/bin/Xvfb")" = 1 ] || { echo "Xvfb: expected one /usr/bin string" >&2; exit 1; }
  sed -i 's#/usr/bin#/tmp/xkb#' "$R/usr/bin/Xvfb"
  touch "$R/.ready"
fi
mkdir -p /tmp/xkb
cat > /tmp/xkb/xkbcomp <<EOF
#!/bin/sh
LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu exec $R/usr/bin/xkbcomp "\$@"
EOF
chmod +x /tmp/xkb/xkbcomp
# OSWorld's mm_agents (run_gui_osworld.py, under the system python) also need backoff
/usr/bin/python3 -c 'import backoff' 2>/dev/null || /usr/bin/python3 -m pip install -q --user --break-system-packages backoff==2.2.1
echo "X tools in $R"

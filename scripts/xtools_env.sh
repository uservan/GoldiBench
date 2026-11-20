# source me: puts the X tools unpacked by scripts/setup_xtools.sh on PATH (no-op where they are installed system-wide).
_R=${VE_LOCAL:-$HOME/.cache/goldibench}/xroot
if ! command -v Xvfb > /dev/null && [ -f "$_R/.ready" ]; then
  export PATH=$_R/usr/bin:$PATH
  export LD_LIBRARY_PATH=$_R/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
  export XKB_DIR=$_R/usr/share/X11/xkb   # desktop.py passes it to Xvfb as -xkbdir
fi
unset _R

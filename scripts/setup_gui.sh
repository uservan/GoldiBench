#!/usr/bin/env bash
# GUI channel: X tools (Xvfb, xdotool, openbox; no root needed) and OSWorld's agents at the commit used in the paper.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
LOCAL=${VE_LOCAL:-$HOME/.cache/goldibench}
bash "$REPO/scripts/setup_xtools.sh"
OSW=$LOCAL/apps/gui_agents/OSWorld
if [ ! -d "$OSW/.git" ]; then
  mkdir -p "$(dirname "$OSW")"
  git clone --filter=blob:none https://github.com/xlang-ai/OSWorld "$OSW"
fi
git -C "$OSW" checkout -q 90a245c0c29ffd417513ea421d84afc2b33df87b
echo "OSWorld agents at $OSW ($(git -C "$OSW" rev-parse --short HEAD))"

#!/usr/bin/env bash
# Download the GoldiBench dataset (HF VanWang/GoldiBench) to $GOLDIBENCH_DATA (default ./data).
# The dataset is fetched as one tar per directory (archives/*.tar, checked against their sha256) and unpacked;
# downloading the ~20k single files instead runs into Hugging Face rate limits.
# Usage: scripts/download_data.sh                    everything (~7 GB)
#        scripts/download_data.sh --apps "gimp blender"   only these apps (+ the shared sources / assets / manuals)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT=${GOLDIBENCH_DATA:-$REPO/data}
mkdir -p "$OUT"
dirs="assets sources manuals minimanual"
apps="darktable rawtherapee gimp inkscape blender"
[ "${1:-}" = --apps ] && apps=$2
for a in $apps; do dirs="$dirs bench_b1_$a bench_b1_${a}_gui"; done
inc=(--include README.md)
for d in $dirs; do inc+=(--include "archives/$d.tar" --include "archives/$d.tar.sha256"); done
hf download VanWang/GoldiBench --repo-type dataset --local-dir "$OUT/.download" "${inc[@]}"
cd "$OUT/.download/archives"
for d in $dirs; do
  [ -f "$d.tar" ] || { echo "missing archives/$d.tar on the hub" >&2; continue; }
  sha256sum -c --quiet "$d.tar.sha256"
  tar -xf "$d.tar" -C "$OUT"
  echo "unpacked $d"
done
cp "$OUT/.download/README.md" "$OUT/" 2>/dev/null || true
echo "data in $OUT  (export GOLDIBENCH_DATA=$OUT; remove $OUT/.download to free space)"

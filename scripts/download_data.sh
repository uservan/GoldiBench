#!/usr/bin/env bash
# Download the GoldiBench dataset (HF VanWang/GoldiBench) to $GOLDIBENCH_DATA (default ./data).
# Usage: scripts/download_data.sh [--apps "gimp blender"]   (default: everything)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT=${GOLDIBENCH_DATA:-$REPO/data}
inc=()
if [ "${1:-}" = --apps ]; then
  for a in $2; do inc+=(--include "bench_b1_$a/*" --include "bench_b1_${a}_gui/*"); done
  inc+=(--include "sources/*" --include "assets/*" --include "manuals/*" --include "minimanual/*")
fi
hf download VanWang/GoldiBench --repo-type dataset --local-dir "$OUT" "${inc[@]}"
echo "data in $OUT  (export GOLDIBENCH_DATA=$OUT)"

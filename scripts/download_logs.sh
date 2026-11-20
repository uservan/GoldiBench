#!/usr/bin/env bash
# Download parts of the run logs (HF VanWang/GoldiBench-logs), laid out as
#   <channel>/<app>/<model>/<condition>/seed<k>/{episodes.parquet, steps.parquet, images.tar, raw.tar.zst}
# Usage: scripts/download_logs.sh [--channel program|gui] [--app APP] [--model MODEL] [--condition COND] [--seed K]
#                                 [--tables-only] [--out DIR]
# Every option defaults to "all" (*). Examples:
#   scripts/download_logs.sh --tables-only                                   # every table (+ runs.csv, cost/)
#   scripts/download_logs.sh --channel gui --app gimp --model gpt61gui       # one model on one app, with screenshots
#   scripts/download_logs.sh --channel program --condition main --seed 0 --tables-only
set -euo pipefail
ch='*' app='*' model='*' cond='*' seed='*' tables=0 out=${GOLDIBENCH_LOGS:-./logs_data}
while [ $# -gt 0 ]; do case $1 in
  --channel) ch=$2; shift 2;; --app) app=$2; shift 2;; --model) model=$2; shift 2;; --condition) cond=$2; shift 2;;
  --seed) seed=$2; shift 2;; --tables-only) tables=1; shift;; --out) out=$2; shift 2;;
  *) echo "unknown option $1" >&2; exit 1;; esac; done
p="$ch/$app/$model/$cond/seed$seed"
inc=(--include "README.md" --include "runs.csv" --include "cost/*" --include "episodes_*.parquet" --include "$p/*.parquet")
[ $tables = 1 ] || inc+=(--include "$p/images.tar" --include "$p/raw.tar.zst")
hf download VanWang/GoldiBench-logs --repo-type dataset --local-dir "$out" "${inc[@]}"
echo "downloaded to $out  (images.tar: WebP at the original paths; raw.tar.zst: tar -I zstd -xf)"

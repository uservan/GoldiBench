#!/usr/bin/env bash
# Restore the paper's runs from the logs dataset (VanWang/GoldiBench-logs) into $GOLDIBENCH_DATA, in the original layout
# (bench_b1_<app>[_gui]/runs/<run>/...), so goldibench/paper/*.py and score.py work on them. Only the raw records are
# fetched (episode.json, scores.json, run logs; no images). Needs the python package zstandard (pip install zstandard). The benchmark itself must be there (scripts/download_data.sh).
# Usage: scripts/restore_runs.sh [--channel program|gui] [--app APP]      (default: everything, a few GB)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT=${GOLDIBENCH_DATA:-$REPO/data}; ch='*' app='*'
while [ $# -gt 0 ]; do case $1 in --channel) ch=$2; shift 2;; --app) app=$2; shift 2;; *) echo "unknown option $1" >&2; exit 1;; esac; done
DL=$OUT/.logs_download
hf download VanWang/GoldiBench-logs --repo-type dataset --local-dir "$DL" \
   --include "$ch/$app/*/*/*/raw.tar.zst" --include "$ch/$app/_run/*/raw.tar.zst" --include "supporting/paper_numbers/raw.tar.zst"
n=0
while IFS= read -r -d '' f; do
  case $f in */supporting/*) dest=$OUT/paper_numbers_original; mkdir -p "$dest";; *) dest=$OUT;; esac   # reference numbers of the paper kept apart
  ${PYTHON:-python3} -c "import sys,tarfile,zstandard
with open(sys.argv[1],'rb') as fh, tarfile.open(fileobj=zstandard.ZstdDecompressor().stream_reader(fh),mode='r|') as t: t.extractall(sys.argv[2],filter='data')" "$f" "$dest"
  n=$((n+1))
done < <(find "$DL" -name raw.tar.zst -print0)
echo "restored $n archives into $OUT (runs under bench_b1_<app>[_gui]/runs/). Remove $DL to free space."

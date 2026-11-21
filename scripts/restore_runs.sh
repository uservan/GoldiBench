#!/usr/bin/env bash
# Restore the paper's runs from the logs dataset (VanWang/GoldiBench-logs) into $GOLDIBENCH_DATA, in the original layout
# (bench_b1_<app>[_gui]/runs/<run>/...), so goldibench/paper/*.py and score.py work on them. By default only the raw
# records are fetched (episode.json, scores.json, run logs; no images) plus the paper's computed numbers
# (-> $GOLDIBENCH_DATA/paper_numbers_original, for comparison). Needs the python package zstandard (pip install zstandard).
# The benchmark itself must be there (scripts/download_data.sh). See docs/paper.md for which script needs what.
# Usage: scripts/restore_runs.sh [--channel program|gui] [--app APP] [--supporting] [--images UNIT]... [--no-runs]
#   --channel / --app  restrict the runs (default: everything, a few GB)
#   --supporting       also the Sec. 2 / Sec. 4 data: motivation/ (audits, judge stress tests), e3/ e3x/ (judged images),
#                      v5/ (human-study pairs, VLM judgements), ~1 GB
#   --images UNIT      also the renders / screenshots of one logs folder, a glob over <channel>/<app>/<model>/<condition>/<seed>,
#                      e.g. 'program/rawtherapee/gpt61sol/main/seed0' (WebP files at the original paths); repeatable
#   --no-runs          skip the raw records (with --supporting / --images to add only those)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT=${GOLDIBENCH_DATA:-$REPO/data}; ch='*' app='*' sup=0 runs=1; imgs=()
while [ $# -gt 0 ]; do case $1 in
  --channel) ch=$2; shift 2;; --app) app=$2; shift 2;; --supporting) sup=1; shift;; --no-runs) runs=0; shift;;
  --images) imgs+=("$2"); shift 2;;
  *) echo "unknown option $1" >&2; exit 1;; esac; done
DL=$OUT/.logs_download
inc=()
[ $runs = 1 ] && inc+=(--include "$ch/$app/*/*/*/raw.tar.zst" --include "$ch/$app/_run/*/raw.tar.zst" --include "supporting/paper_numbers/raw.tar.zst")
[ $sup = 1 ] && for s in motivation_repo motivation_e3 motivation_e3x validation_v5; do inc+=(--include "supporting/$s/*"); done
for u in ${imgs[@]+"${imgs[@]}"}; do inc+=(--include "$u/images.tar"); done
[ ${#inc[@]} -gt 0 ] || { echo "nothing to restore" >&2; exit 1; }
hf download VanWang/GoldiBench-logs --repo-type dataset --local-dir "$DL" "${inc[@]}"
untar() {   # archive, destination, [member prefix to strip]
  ${PYTHON:-python3} -c "import sys,tarfile
f=sys.argv[1];strip=sys.argv[3] if len(sys.argv)>3 else ''
if f.endswith('.zst'):
  import zstandard;fh=zstandard.ZstdDecompressor().stream_reader(open(f,'rb'))
else:fh=open(f,'rb')
with tarfile.open(fileobj=fh,mode='r|') as t:
  for m in t:
    if strip:
      if not m.name.startswith(strip):continue
      m.name=m.name[len(strip):]
    t.extract(m,sys.argv[2],filter='data')" "$@"
}
n=0
want() {   # is this archive one of the requested ones?
  case $1 in
    */supporting/paper_numbers/*) [ $runs = 1 ];;
    */supporting/*) [ $sup = 1 ];;
    */images.tar) for u in ${imgs[@]+"${imgs[@]}"}; do case ${1#$DL/} in $u/images.tar) return 0;; esac; done; return 1;;
    *) [ $runs = 1 ] && case ${1#$DL/} in $ch/$app/*) true;; *) false;; esac;;
  esac
}
while IFS= read -r -d '' f; do
  want "$f" || continue
  case $f in
    */supporting/paper_numbers/*) mkdir -p "$OUT/paper_numbers_original"   # reference numbers of the paper kept apart
      untar "$f" "$OUT/paper_numbers_original"
      untar "$f" "$OUT/paper_numbers_original" "visual-effect-skills/";;   # logs/threshold_sweep.json sits under this prefix
    */supporting/motivation_repo/*) mkdir -p "$OUT/motivation"; untar "$f" "$OUT/motivation" "visual-effect-skills/motivation/";;
    *) untar "$f" "$OUT";;
  esac
  n=$((n+1))
done < <(find "$DL" \( -name raw.tar.zst -o -name images.tar \) -print0)
echo "restored $n archives into $OUT (runs under bench_b1_<app>[_gui]/runs/). Remove $DL to free space."

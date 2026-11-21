#!/usr/bin/env bash
# Data of the judge / human-study experiments (paper Sec. 2 and Sec. 4.1; docs/judges.md) into $GOLDIBENCH_DATA/supporting:
#   - supporting/<unit>/ of the logs dataset VanWang/GoldiBench-logs (judgments, manifests, pairs, human ratings, candidate
#     images; ~0.8 GB), unpacked in place; a PNG is written next to every released WebP image
#   - PSBench's judge code (github.com/zyn1216/PSBench @ 5a9a911) -> supporting/PSBench
#   - PSBench's task folders (HF zyn1216/PSBench @ 929d071, no videos): the 60 E3 tasks, or all 600 with --psbench-all (C1)
# Usage: scripts/download_supporting.sh [--psbench-all] [--no-images]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
DATA=${GOLDIBENCH_DATA:-$REPO/data}; SUP=${GOLDIBENCH_SUPPORTING:-$DATA/supporting}; PY=${PYTHON:-python3}
ALL=0 IMAGES=1
while [ $# -gt 0 ]; do case $1 in --psbench-all) ALL=1; shift;; --no-images) IMAGES=0; shift;; *) echo "unknown option $1" >&2; exit 1;; esac; done
export HF_HUB_DISABLE_XET=${HF_HUB_DISABLE_XET:-1}
mkdir -p "$SUP"; DL=$SUP/.download
inc=(--include "supporting/*/raw.tar.zst" --include "supporting/validation_v5/human_ratings.jsonl")
[ $IMAGES = 1 ] && inc+=(--include "supporting/*/images.tar")
hf download VanWang/GoldiBench-logs --repo-type dataset --local-dir "$DL" "${inc[@]}"
for d in "$DL"/supporting/*/; do
  u=$(basename "$d"); mkdir -p "$SUP/$u"
  [ -s "$d/raw.tar.zst" ] && $PY -c "import sys,tarfile,zstandard
with open(sys.argv[1],'rb') as fh, tarfile.open(fileobj=zstandard.ZstdDecompressor().stream_reader(fh),mode='r|') as t: t.extractall(sys.argv[2],filter='data')" "$d/raw.tar.zst" "$SUP/$u" || true
  [ -f "$d/images.tar" ] && tar -xf "$d/images.tar" -C "$SUP/$u"
  echo "unpacked $u"
done
if [ -f "$DL/supporting/validation_v5/human_ratings.jsonl" ]; then
  mkdir -p "$SUP/validation_v5/v5"; cp "$DL/supporting/validation_v5/human_ratings.jsonl" "$SUP/validation_v5/v5/"
else echo "WARNING: supporting/validation_v5/human_ratings.jsonl not found in the logs dataset (needed by human_agreement.py)" >&2; fi
[ $IMAGES = 1 ] && (cd "$REPO" && $PY -m goldibench.judge.common webp2png)
[ -d "$SUP/PSBench/.git" ] || git clone -q https://github.com/zyn1216/PSBench "$SUP/PSBench"
git -C "$SUP/PSBench" checkout -q 5a9a911
if [ $ALL = 1 ]; then
  hf download zyn1216/PSBench --repo-type dataset --revision 929d0710eb7c86a988f8a69a74619052b60ac293 --local-dir "$SUP/PSBench-data" --exclude "*.mp4" --exclude "README.md" --exclude ".gitattributes"
else
  ids=$(cut -d, -f1 "$SUP/motivation_repo/visual-effect-skills/motivation/e3/candidates_manifest.csv" | sed 1d | sort -u)
  args=(); for i in $ids; do args+=(--include "$i/*"); done
  hf download zyn1216/PSBench --repo-type dataset --revision 929d0710eb7c86a988f8a69a74619052b60ac293 --local-dir "$SUP/PSBench-data" "${args[@]}" --exclude "*.mp4"
fi
(cd "$REPO" && $PY -m goldibench.judge.common paths)
echo "supporting data in $SUP. Remove $DL to free space."

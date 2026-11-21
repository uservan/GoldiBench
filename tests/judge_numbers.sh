#!/usr/bin/env bash
# Paper Sec. 2 and Sec. 4.1 numbers from the released judgments and human ratings (docs/judges.md). No GPU, seconds.
# Needs scripts/download_supporting.sh (--no-images is enough).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
$PY -m goldibench.judge.motivation_numbers --check
$PY -m goldibench.judge.human_agreement --check
echo "JUDGE NUMBERS OK"

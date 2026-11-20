#!/usr/bin/env bash
# Smoke test of the Sec. 5 interventions (program channel, L2): one task of the intervention subset per app, 2 rounds,
# every condition flag of the paper. Same setup as tests/smoke.sh (GOLDIBENCH_DATA, apps, MODEL).
# Usage: MODEL=holo4_35b APPS="gimp darktable" tests/interventions.sh
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
SRC=${GOLDIBENCH_DATA:?set GOLDIBENCH_DATA}; MODEL=${MODEL:-holo4_35b}; PY=${PYTHON:-python3}
SMOKE_DIR=${SMOKE_DIR:-$(mktemp -d /tmp/goldibench_interv.XXXX)}; mkdir -p "$SMOKE_DIR"
export GOLDIBENCH_MODELS=${GOLDIBENCH_MODELS:-$REPO/configs/smoke.yaml}
APPS=${APPS:-"gimp darktable"}
for d in sources assets manuals minimanual; do [ -e "$SRC/$d" ] && ln -sfn "$SRC/$d" "$SMOKE_DIR/$d"; done
for a in $APPS; do mkdir -p "$SMOKE_DIR/bench_b1_$a/runs"
  for f in "$SRC/bench_b1_$a"/*; do [ "$(basename "$f")" = runs ] || ln -sfn "$f" "$SMOKE_DIR/bench_b1_$a/$(basename "$f")"; done; done
export GOLDIBENCH_DATA=$SMOKE_DIR
fail=0
for a in $APPS; do
  head -1 "$SRC/minimanual/subsets/$a.txt" > "$SMOKE_DIR/one_$a.txt"
  declare -A C=([manual]="--manual" [table]="--knowledge table_state" [tdiff]="--knowledge table_state_diff"
                [diffimg]="--knowledge diff_image" [mmv]="--minimanual visual" [mmt]="--minimanual text"
                [forced]="--forced" [fb]="--forced --feedback numeric")
  for c in manual table tdiff diffimg mmv mmt forced fb; do
    BENCH_APP=$a BENCH_SET=bench_b1_$a $PY "$REPO/goldibench/bench/run_agent.py" --models "$MODEL" --levels L2 \
      --tasks-file "$SMOKE_DIR/one_$a.txt" --run "iv_$c" --rounds 2 --max-tokens 8000 --concurrency 1 ${C[$c]} \
      > "$SMOKE_DIR/$a.$c.log" 2>&1 || { echo "FAIL $a $c (see $SMOKE_DIR/$a.$c.log)"; fail=1; continue; }
    e=$(ls "$SMOKE_DIR"/bench_b1_$a/runs/iv_$c/*/L2_*/episode.json 2>/dev/null | head -1)
    $PY - "$e" "$a" "$c" <<'P'
import json, sys
e = json.load(open(sys.argv[1])); r = e['rounds']
kinds = [('tool:' + x['tool']) if 'tool' in x else ('error' if 'error' in x else 'program') for x in r]
print(f"   {sys.argv[2]:12s} {sys.argv[3]:8s} rounds: {kinds}")
P
    grep -lE '"error": "render failed"|"exception":' "$e" > /dev/null && { echo "FAIL $a $c: harness error"; fail=1; }
  done
done
[ $fail = 0 ] && echo "INTERVENTIONS OK" || { echo "INTERVENTIONS FAILED"; exit 1; }

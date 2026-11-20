#!/usr/bin/env bash
# End-to-end smoke test: program channel on all five apps (1 task, L1 + L2, 2 rounds) and, unless SKIP_GUI=1, the GUI
# channel on darktable (1 task, L1, 15 steps); every episode is scored with the paper's rule.
# Needs: the dataset (GOLDIBENCH_DATA, scripts/download_data.sh), the apps (scripts/setup_apps.sh), an OpenAI-compatible
# model endpoint named in configs (default: holo4_35b from configs/smoke.yaml at localhost:8011).
# Runs go to a scratch copy ($SMOKE_DIR, symlinks to the dataset), never into the dataset itself.
# Usage: MODEL=holo4_35b tests/smoke.sh
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
SRC=${GOLDIBENCH_DATA:?set GOLDIBENCH_DATA to the downloaded dataset}
MODEL=${MODEL:-holo4_35b}
GUI_MODEL=${GUI_MODEL:-holo4_35b}
SMOKE_DIR=${SMOKE_DIR:-$(mktemp -d /tmp/goldibench_smoke.XXXX)}
PY=${PYTHON:-python3}
export GOLDIBENCH_MODELS=${GOLDIBENCH_MODELS:-$REPO/configs/smoke.yaml}
APPS=${APPS:-"darktable rawtherapee gimp inkscape blender"}

# scratch data dir: everything links to the dataset, only runs/ is real
for d in sources assets manuals minimanual; do [ -e "$SRC/$d" ] && ln -sfn "$SRC/$d" "$SMOKE_DIR/$d"; done
for a in $APPS; do
  for s in bench_b1_$a bench_b1_${a}_gui; do
    [ -d "$SRC/$s" ] || continue; mkdir -p "$SMOKE_DIR/$s/runs"
    for f in "$SRC/$s"/*; do [ "$(basename "$f")" = runs ] || ln -sfn "$f" "$SMOKE_DIR/$s/$(basename "$f")"; done
  done
done
export GOLDIBENCH_DATA=$SMOKE_DIR
echo "smoke data: $SMOKE_DIR  model: $MODEL"

fail=0
for a in $APPS; do
  echo "== program channel: $a"
  BENCH_APP=$a BENCH_SET=bench_b1_$a $PY "$REPO/goldibench/bench/run_agent.py" --models "$MODEL" --levels L1 L2 \
    --run smoke --limit 1 --rounds 2 --max-tokens 8000 --concurrency 2 || { echo "FAIL run $a"; fail=1; continue; }
  BENCH_APP=$a BENCH_SET=bench_b1_$a $PY "$REPO/goldibench/bench/score.py" --run smoke > "$SMOKE_DIR/score_$a.txt" 2>&1 \
    || { echo "FAIL score $a"; tail -5 "$SMOKE_DIR/score_$a.txt"; fail=1; continue; }
  $PY - "$SMOKE_DIR/bench_b1_$a/runs/smoke/scores.json" <<'E'
import json,sys
for e in json.load(open(sys.argv[1]))['episodes']:
    print(f"   {e['task_id']} {e['level']} {e['model']}: pass={e['pass']} closeness={e['closeness']:.3f} rounds={e['rounds']}")
E
done

if [ "${SKIP_GUI:-0}" != 1 ]; then
  echo "== GUI channel: darktable"
  source "$REPO/scripts/xtools_env.sh"
  BENCH_APP=darktable $PY "$REPO/goldibench/gui/run_gui_osworld.py" --models "$GUI_MODEL" --levels L1 --tasks b000 \
    --run smoke --max-steps 15 --concurrency 1 || { echo "FAIL gui"; fail=1; }
  for e in "$SMOKE_DIR"/bench_b1_darktable_gui/runs/smoke/*/episode.json; do
    [ -f "$e" ] && $PY -c "import json,sys;e=json.load(open(sys.argv[1]));print('  ',e['id'],e['model'],e['end'],e['n_steps'],'steps pass=',e['eval'].get('pass'),'closeness=',e['eval'].get('closeness'))" "$e"
  done
fi
# an episode without a rendered round means the app or the model call failed, whatever the score says
bad=$(grep -lE '"rounds": \[\]|"error": "(render failed|no valid reply)"' "$SMOKE_DIR"/bench_b1_*/runs/smoke/*/*/episode.json 2>/dev/null || true)
[ -n "$bad" ] && { echo "episodes without a rendered round:"; echo "$bad"; fail=1; }
[ $fail = 0 ] && echo "SMOKE OK" || { echo "SMOKE FAILED"; exit 1; }

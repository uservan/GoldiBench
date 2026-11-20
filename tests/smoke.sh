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
SMOKE_DIR=${SMOKE_DIR:-$(mktemp -d /tmp/goldibench_smoke.XXXX)}; mkdir -p "$SMOKE_DIR"
PY=${PYTHON:-python3}
export GOLDIBENCH_MODELS=${GOLDIBENCH_MODELS:-$REPO/configs/smoke.yaml}
APPS=${APPS:-"darktable rawtherapee gimp inkscape blender"}

# scratch data dir: everything links to the dataset, only runs/ is real
for d in sources assets manuals minimanual; do [ -e "$SRC/$d" ] && ln -sfn "$SRC/$d" "$SMOKE_DIR/$d"; done
for a in $(echo $APPS ${GUI_APPS:-darktable} | tr " " "\n" | sort -u); do
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
  source "$REPO/scripts/xtools_env.sh"
  for ga in ${GUI_APPS:-darktable}; do
    echo "== GUI channel: $ga"
    BENCH_APP=$ga $PY "$REPO/goldibench/gui/run_gui_osworld.py" --models "$GUI_MODEL" --levels L1 --tasks b000 \
      --run smoke --max-steps ${GUI_STEPS:-15} --concurrency 1 || { echo "FAIL gui $ga"; fail=1; }
    for e in "$SMOKE_DIR"/bench_b1_${ga}_gui/runs/smoke/*/episode.json; do
      [ -f "$e" ] && $PY -c "import json,sys;e=json.load(open(sys.argv[1]));print('  ',e['id'],e['model'],e['end'],e['n_steps'],'steps pass=',e['eval'].get('pass'),'closeness=',e['eval'].get('closeness'))" "$e"
    done
  done
fi
# harness failures (not model failures): a render that failed, a model call that raised (server down, bad request), a
# GUI harness error or agent exception. A model that answers badly (e.g. reasoning hits --max-tokens) is a valid result.
bad=$( { grep -lE '"error": "render failed"|"exception":' "$SMOKE_DIR"/bench_b1_*/runs/smoke/*/*/episode.json
         grep -lE '"response": "agent error|"end": "harness error"' "$SMOKE_DIR"/bench_b1_*_gui/runs/smoke/*/episode.json
         ls "$SMOKE_DIR"/bench_b1_*_gui/runs/smoke/*/harness_error.json; } 2>/dev/null || true)
[ -n "$bad" ] && { echo "harness failures in:"; echo "$bad"; fail=1; }
[ $fail = 0 ] && echo "SMOKE OK" || { echo "SMOKE FAILED"; exit 1; }

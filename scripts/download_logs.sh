#!/usr/bin/env bash
# Download parts of the run logs (HF VanWang/GoldiBench-logs); everything is split by run, so pick what you need.
# Usage: scripts/download_logs.sh [--part tables|images|raw|all] [--app APP] [--run RUN] [--gui|--program] [--paper-only] [--out DIR]
#   --part tables   merged tables (data/), runs.csv, cost/ (default; small)
#   --part images   WebP renders / screenshots of the selected runs
#   --part raw      original records (episode.json, scores.json, logs) of the selected runs
#   --app gimp --run b1t32       one app / one run name (shell patterns allowed, e.g. --run 'b1g100_s*')
#   --paper-only    only the runs used in the paper (needs runs.csv, fetched automatically)
# Examples:
#   scripts/download_logs.sh                                         # all tables
#   scripts/download_logs.sh --part images --app gimp --run b1g100_s0 --gui
#   scripts/download_logs.sh --part raw --paper-only --app darktable
set -euo pipefail
part=tables app='*' run='*' chan='' paper=0 out=${GOLDIBENCH_LOGS:-./logs_data}
while [ $# -gt 0 ]; do case $1 in
  --part) part=$2; shift 2;; --app) app=$2; shift 2;; --run) run=$2; shift 2;;
  --gui) chan=_gui; shift;; --program) chan=__P; shift;; --paper-only) paper=1; shift;; --out) out=$2; shift 2;;
  *) echo "unknown option $1" >&2; exit 1;; esac; done
REPO=VanWang/GoldiBench-logs
get(){ hf download "$REPO" --repo-type dataset --local-dir "$out" "$@"; }
if [ "$part" = tables ] || [ "$part" = all ]; then get --include "data/*" --include "data/*/*" --include "runs.csv" --include "cost/*" --include "README.md"; fi
[ "$part" = tables ] && { echo "tables in $out"; exit 0; }
case $chan in _gui) c="bench_b1_${app}_gui";; __P) c="bench_b1_${app}";; *) c="bench_b1_${app}*";; esac
units=("${c}__runs__${run}")
if [ $paper = 1 ]; then
  get --include runs.csv > /dev/null
  mapfile -t units < <(python3 - "$out/runs.csv" "$c" "$run" <<'E'
import csv, fnmatch, sys
f, c, r = sys.argv[1:]
for row in csv.DictReader(open(f)):
    u = row['unit']
    if row['in_paper'] == 'True' and fnmatch.fnmatch(u, f'{c}__runs__{r}') and (c.endswith('*') or not u.split('__runs__')[0].endswith('_gui') or c.endswith('_gui')):
        print(u)
E
)
  [ ${#units[@]} -gt 0 ] || { echo "no paper runs match" >&2; exit 1; }
fi
inc=()
for u in "${units[@]}"; do
  [ "$part" = images ] || [ "$part" = all ] && inc+=(--include "images/$u.tar" --include "images/$u.part*.tar")
  [ "$part" = raw ] || [ "$part" = all ] && inc+=(--include "raw/$u.*")
done
get "${inc[@]}"
echo "downloaded to $out  (images/*.tar: WebP files at their original paths; raw/*.tar.zst: tar -I zstd -xf)"

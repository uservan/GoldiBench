"""Text report of a scored run (the table goldibench/bench/score.py prints after scoring), written from an existing
runs/<run>/scores.json, without re-rendering: no application needed, so it works on runs restored from the logs dataset
(scripts/restore_runs.sh). qwen_seeds_l2.py and sec43_data.py read these reports.
  python goldibench/paper/score_report.py                  -> <data>/logs/bench_b1_<app>_scores_<run>.txt for every
                                                              restored program run of the five apps
  python goldibench/paper/score_report.py --app gimp --run b1t32     (one report, also printed)"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import argparse, json, statistics as st
import gbpaths

APPS = ['darktable', 'rawtherapee', 'gimp', 'inkscape', 'blender']
MIN_CLOSE, MAX_DE = 0.75, 4.0                      # make_pilot.MIN_CLOSE / MAX_DE (the pass rule)
THRESH = [0.5 * i for i in range(1, 21)]           # score.THRESH


def report(scores, run):
    rows = scores['episodes']; out = []
    if scores.get('validation'):
        v = list(scores['validation'].values())
        def passed(d, d0): return d <= MAX_DE and 1 - d / d0 >= MIN_CLOSE
        def fr(k, f):
            a = [x for x in v if x.get(k) is not None]
            return f'{100*sum(not f(x[k], x["start"]) for x in a)/len(a):.0f}% of {len(a)}' if a else 'n/a'
        out.append('VALIDATION  oracle max dE %.3f | fail rate (should be 0): x0.9 %s  x1.1 %s | fail rate (should be 100%%): identity %s  half %s  over %s' % (
            max(x['oracle'] for x in v), fr('near_0.9', passed), fr('near_1.1', passed), fr('start', passed), fr('half', passed), fr('over', passed)))
    out.append(f"run {run}: {len(rows)} episodes, pass = closeness>={MIN_CLOSE} and dE<={MAX_DE}")
    out.append(f"{'model':7s} {'level':5s} {'kind':7s} {'n':>3s} {'fail':>4s} {'pass%':>6s} {'dE<=3%':>6s} {'auc':>5s} {'closeness':>9s} {'dE med':>7s} {'r1->final dE':>13s}")
    for m in sorted({r['model'] for r in rows}):
        for l in ['L1', 'L2', 'L3']:
            for k in ['single', 'multi', 'long', 'all']:
                s = [r for r in rows if r['model'] == m and r['level'] == l and (k == 'all' or r['kind'] == k)]
                if not s: continue
                first = [r['per_round'][0] for r in s if r.get('per_round')]
                out.append(f"{m:7s} {l:5s} {k:7s} {len(s):3d} {sum(r.get('failed',False) for r in s):4d} {100*sum(r['pass'] for r in s)/len(s):6.0f} {100*sum(r['de00']<=3 for r in s)/len(s):6.0f} "
                           f"{st.mean(st.mean(r['de00']<=t for r in s) for t in THRESH):5.2f} {st.mean(r['closeness'] for r in s):9.2f} "
                           f"{st.median(r['de00'] for r in s):7.2f} {st.median(first) if first else float('nan'):6.2f}->{st.median(r['de00'] for r in s):5.2f}")
    return '\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--app'); ap.add_argument('--run'); a = ap.parse_args()
    D = gbpaths.DATA; L = D / 'logs'; L.mkdir(parents=True, exist_ok=True); n = 0
    for app in ([a.app] if a.app else APPS):
        runs = D / f'bench_b1_{app}' / 'runs'
        for f in sorted(runs.glob(f'{a.run or "*"}/scores.json')):
            txt = report(json.loads(f.read_text()), f.parent.name)
            (L / f'bench_b1_{app}_scores_{f.parent.name}.txt').write_text(txt); n += 1
            if a.run: print(txt, end='')
    print(f'wrote {n} reports to {L}', file=_sys.stderr)


if __name__ == '__main__':
    main()

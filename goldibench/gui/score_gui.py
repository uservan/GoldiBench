"""Summarise a GUI bench run (runs/<--run>/*/episode.json): pass rate with task-level bootstrap 95 % CI, closeness,
dE, steps, how episodes ended, and gate failures, per model x level x kind. The evaluation itself happens in the
episode (env.evaluate), so this only aggregates."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,json,math,random,statistics as st
from collections import Counter
import os
if os.environ.get('BENCH_APP')=='gimp':from make_gimp_gui_tasks import OUT
elif os.environ.get('BENCH_APP') in ('inkscape','rawtherapee','blender'):
    from pathlib import Path;OUT=gbpaths.DATA/os.environ.get('GUI_OUT',f"bench_b1_{os.environ['BENCH_APP']}_gui")
else:from make_gui_tasks import OUT

def ci(xs,n=4000,seed=0):
    if not xs:return (0,0)
    # math.fsum / len instead of statistics.mean (exact Fractions: ~1 h per run with 4000 resamples, 2026-11-11)
    r=random.Random(seed);k=len(xs);b=sorted(math.fsum(xs[r.randrange(k)] for _ in xs)/k for _ in range(n))
    return round(100*b[int(0.025*n)]),round(100*b[int(0.975*n)])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',default='g1')
    ap.add_argument('--base',help='also compare per task with this run');a=ap.parse_args()
    eps=[json.loads(p.read_text()) for p in sorted((OUT/'runs'/a.run).glob('*/episode.json'))]
    print(f'run {a.run}: {len(eps)} episodes, pass = closeness>=0.75 and dE<=4 on our re-render of the GUI edit')
    print('model   level kind      n  pass% [95% CI]  closeness  dE med  steps  ends')
    for m in sorted({e['model'] for e in eps}):
        for lv in ('L1','L2','L3'):
            for kind in ('single','multi','all'):
                g=[e for e in eps if e['model']==m and e['level']==lv and (kind=='all' or e['kind']==kind)]
                if not g:continue
                p=[float(bool(e['eval'].get('pass'))) for e in g]
                cl=[e['eval'].get('closeness',0.0) for e in g];de=[e['eval']['de00'] for e in g if 'de00' in e['eval']]
                ends=Counter(e['end'] if not e['eval'].get('gate') else 'gate' for e in g)
                lo,hi=ci(p)
                print(f"{m:7} {lv:5} {kind:7} {len(g):3} {100*st.mean(p):6.0f} [{lo:3},{hi:3}] {st.mean(cl):9.2f} {st.median(de) if de else float('nan'):7.2f} "
                      f"{st.mean(e['n_steps'] for e in g):6.1f}  {dict(ends)}")
    gates=Counter(e['eval']['gate'][:60] for e in eps if e['eval'].get('gate'))
    if gates:print('gate failures:',dict(gates))
    if a.base:paired(a.base,a.run,eps)

def paired(base,run,eps):
    # same task, same model: Δ pass with bootstrap 95 % CI (points), rescued / broken, Δ closeness with CI
    b={(e['model'],e['id']):e for e in (json.loads(p.read_text()) for p in (OUT/'runs'/base).glob('*/episode.json'))}
    print(f'\npaired {run} vs {base}: Δpass [95% CI]  +/-  Δcloseness [95% CI]')
    for m in sorted({e['model'] for e in eps}):
        for lv in ('L1','L2','L3'):
            pair=[(b[(m,e['id'])]['eval'],e['eval']) for e in eps if e['model']==m and e['level']==lv and (m,e['id']) in b]
            if not pair:continue
            dp=[int(bool(y.get('pass')))-int(bool(x.get('pass'))) for x,y in pair]
            dc=[y.get('closeness',0.0)-x.get('closeness',0.0) for x,y in pair]
            lo,hi=ci(dp);clo,chi=ci(dc)
            print(f"{m:7} {lv:5} {100*st.mean(dp):+4.0f} [{lo:+4},{hi:+4}]  +{sum(d>0 for d in dp)}/-{sum(d<0 for d in dp)}  "
                  f"{st.mean(dc):+.2f} [{clo/100:+.2f},{chi/100:+.2f}]  (n={len(pair)})")

if __name__=='__main__':main()

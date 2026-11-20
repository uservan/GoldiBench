"""Sec. 4.3 data (user 2026-11-14): Qwen3.5 dense 2B / 4B / 9B / 27B, OpenCUA 7B / 32B / 72B, UI-TARS 2B / 7B / 72B.
GUI channel, 100 steps, runs b1g100_s0..2 of all five bench_b1_<app>_gui. Per model and level: pass % per app (mean over seeds),
then the mean over the five apps (each app weighs the same), as mean and sd over seeds (as fig_scaling.py); also the five-app
mean closeness (gate failures 0, clipped at -1, as mv_analysis.py) and the number of episodes per cell.
Program channel for the same Qwen3.5 sizes (b1t32 seeds 0-4, scores files, as fig_scaling.program) for reference.
Output: logs/sec43_data.json and logs/sec43_data.md."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,os,statistics as st
from concurrent.futures import ThreadPoolExecutor
D=str(gbpaths.DATA);L=f'{D}/logs'
APPS=('gimp','darktable','rawtherapee','blender','inkscape');LEVELS=('L1','L2','L3');SEEDS='012'
FAM=[('Qwen3.5 (dense)',[('2B','qwen35gui_2b'),('4B','qwen35gui_4b'),('9B','qwen35gui_9b'),('27B','qwen35gui_27b')]),
     ('OpenCUA',[('7B','opencua_7b'),('32B','opencua_32b'),('72B','opencua_72b')]),
     ('UI-TARS',[('2B','uitars_2b'),('7B','uitars_7b'),('72B','uitars_72b')])]
MODELS=[m for _,ms in FAM for _,m in ms]
N={}
for a in APPS:
    for l in gbpaths.open_tasks(f'{D}/bench_b1_{a}_gui/tasks.jsonl'):
        t=json.loads(l);lv=t.get('level') or t['id'].split('_')[-1];N[a,lv]=N.get((a,lv),0)+1

def read(p):
    try:e=json.load(open(p));ev=e.get('eval') or {};return bool(ev.get('pass')),max(-1.0,float(ev.get('closeness') or 0.0))
    except Exception:return None
jobs=[]
for a in APPS:
    for s in SEEDS:
        R=f'{D}/bench_b1_{a}_gui/runs/b1g100_s{s}'
        for d in os.listdir(R):
            parts=d.split('_',2)
            if len(parts)==3 and parts[1] in LEVELS and parts[2] in MODELS:jobs.append((a,parts[2],parts[1],s,f'{R}/{d}/episode.json'))
with ThreadPoolExecutor(64) as ex:vals=list(ex.map(lambda j:read(j[4]) if os.path.exists(j[4]) else None,jobs))
cell={}
for (a,m,lv,s,_),v in zip(jobs,vals):
    if v is not None:cell.setdefault((a,m,lv,s),[]).append(v)

# user 2026-11-14: an episode without episode.json (the model left the app hung, e.g. GIMP L3 Oilify, so the result could not
# be exported even after two reruns) counts as a failure: pass False, closeness 0.
PADDED={}
for a in APPS:
    for m in MODELS:
        for lv in LEVELS:
            for s in SEEDS:
                k=(a,m,lv,s);miss=N[a,lv]-len(cell.get(k,[]))
                if miss>0:cell.setdefault(k,[]).extend([(False,0.0)]*miss);PADDED[k]=miss

def pct(xs):return 100*st.mean(p for p,_ in xs)
out={}
for m in MODELS:
    for lv in LEVELS:
        per_seed=[st.mean(pct(cell[a,m,lv,s]) for a in APPS) for s in SEEDS if all(cell.get((a,m,lv,s)) for a in APPS)]
        per_app={a:round(st.mean(pct(cell[a,m,lv,s]) for s in SEEDS if cell.get((a,m,lv,s))),1) for a in APPS}
        clo=st.mean(st.mean(c for s in SEEDS for _,c in cell.get((a,m,lv,s),[])) for a in APPS)
        n={a:sum(len(cell.get((a,m,lv,s),[])) for s in SEEDS) for a in APPS}
        out[f'{m}|{lv}']={'mean5':round(st.mean(per_seed),2),'sd_seeds':round(st.stdev(per_seed),2) if len(per_seed)>1 else 0.0,
                          'per_app':per_app,'closeness5':round(clo,3),'n':n,'n_expected':{a:3*N[a,lv] for a in APPS}}

prog={}
for s in range(5):
    for a in APPS:
        for line in open(f'{L}/bench_b1_{a}_scores_b1t32{"" if s==0 else f"_s{s}"}.txt'):
            p=line.split()
            if len(p)>=8 and p[2]=='all' and p[1] in LEVELS:prog[p[0],p[1],s,a]=float(p[5])
pq={}
for sz in ('2b','4b','9b','27b'):
    m=f'qwen35_{sz}'
    for lv in LEVELS:
        per=[st.mean(prog[m,lv,s,a] for a in APPS) for s in range(5) if all((m,lv,s,a) in prog for a in APPS)]
        pq[f'{m}|{lv}']={'mean5':round(st.mean(per),2),'sd_seeds':round(st.stdev(per),2),'n_seeds':len(per)}
json.dump({'gui':out,'program_qwen':pq},open(f'{L}/sec43_data.json','w'),indent=1)

md=['# Sec. 4.3 data (GUI channel, 100 steps, seeds 0-2; 5-app mean = each app weighs the same)','',
    '| family | size | L1 | L2 | L3 | L1 gimp / dt / rt / bl / ink | closeness L1 / L2 / L3 |','|---|---|---|---|---|---|---|']
for fam,ms in FAM:
    for sz,m in ms:
        c=[out[f'{m}|{lv}'] for lv in LEVELS]
        md.append(f"| {fam} | {sz} | "+' | '.join(f"{x['mean5']:.1f} ± {x['sd_seeds']:.1f}" for x in c)+' | '+
                  ' / '.join(f"{c[0]['per_app'][a]:.0f}" for a in APPS)+' | '+' / '.join(f"{x['closeness5']:+.2f}" for x in c)+' |')
md+=['','GIMP only (pass %, mean over seeds):','','| family | size | L1 | L2 | L3 |','|---|---|---|---|---|']
for fam,ms in FAM:
    for sz,m in ms:md.append(f'| {fam} | {sz} | '+' | '.join(f"{out[f'{m}|{lv}']['per_app']['gimp']:.1f}" for lv in LEVELS)+' |')
md+=['','Program channel, Qwen3.5 (b1t32, 5 seeds, 5-app mean):','','| size | L1 | L2 | L3 |','|---|---|---|---|']
for sz in ('2b','4b','9b','27b'):md.append(f'| {sz.upper()} | '+' | '.join(f"{pq[f'qwen35_{sz}|{lv}']['mean5']:.1f} ± {pq[f'qwen35_{sz}|{lv}']['sd_seeds']:.1f}" for lv in LEVELS)+' |')
md+=['','Episodes counted as failures (no episode.json: app hung, result not exportable): '+
    ('; '.join(f'{m} {lv} {a} s{s}: {n}' for (a,m,lv,s),n in sorted(PADDED.items())) if PADDED else 'none')]
open(f'{L}/sec43_data.md','w').write('\n'.join(md)+'\n');print('\n'.join(md))

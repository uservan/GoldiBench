"""Numbers of Sec. 5 (tab:main pooled rows, tab:interventions paired tests, rounds, loose rule). Run with the vllm env (scipy)."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,collections,statistics as st,sys
from scipy.stats import binomtest,wilcoxon
D=str(gbpaths.DATA)
APPS=['darktable','rawtherapee','gimp','inkscape','blender']
def load(run):
    E={}
    for a in APPS:
        try:S=json.load(open(f'{D}/bench_b1_{a}/runs/{run}/scores.json'))['episodes']
        except FileNotFoundError:continue
        for e in S:E[(a,e['task_id'],e['level'],e['model'])]=e
    return E
B=load('b1t32')
print('== b1t32 models',sorted({k[3] for k in B}))
# pooled per model/level
for lv in ('L1','L2','L3'):
    row=collections.defaultdict(list)
    for k,e in B.items():
        if k[2]==lv:row[k[3]].append(e)
    print(lv,' '.join(f"{m}:{100*st.mean(x['pass'] for x in v):.1f}/{st.mean(x['closeness'] for x in v):+.2f}" for m,v in sorted(row.items())))
def paired(run,models=None,levels=('L2',),base=B):
    R=load(run);P=[(base[k],R[k]) for k in R if k in base and k[2] in levels and (models is None or k[3] in models)]
    up=sum(1 for b,r in P if r['pass'] and not b['pass']);dn=sum(1 for b,r in P if b['pass'] and not r['pass'])
    d=[r['closeness']-b['closeness'] for b,r in P]
    p=binomtest(up,up+dn).pvalue if up+dn else 1
    w=wilcoxon(d).pvalue if any(d) else 1
    mods=sorted({k[3] for k in R if k[2] in levels})
    bp=100*st.mean(b['pass'] for b,r in P);rp=100*st.mean(r['pass'] for b,r in P)
    print(f"{run:22s} {','.join(models or mods)[:40]:40s} n={len(P)} pass {bp:.1f}->{rp:.1f} +{up}/-{dn} p={p:.3g} dclose med {st.median(d):+.3f} p={w:.2g}")
    return P
print('== interventions (paired vs b1t32, L2)')
for run in ('b1man','b1mmv','b1mmt','b1table','b1tdiff'):
    paired(run,['qwen35','glm53'])
for run in ('b1tdiff',):
    for m in ('opus55','gpt61sol'):paired(run,[m])
print('== feedback / forced, open models pooled and closed')
OPEN=['dsv41','glm53','nemo35','step37','qwen35','qwen35_0.8b','qwen35_2b','qwen35_4b','qwen35_9b','qwen35_27b','qwen35_35b_a3b','qwen35_122b_a10b']
for run in ('b1forced','b1fb'):
    for lv in ('L2','L3'):
        paired(run,OPEN,(lv,))
        for m in ('opus55','gpt61sol'):paired(run,[m],(lv,))
# fb vs forced (numeric feedback alone)
F=load('b1forced')
for lv in ('L2','L3'):
    for ms,name in ((OPEN,'open'),(['opus55'],'opus'),(['gpt61sol'],'gpt')):
        paired('b1fb',ms,(lv,),base=F)
print('== rounds used in b1t32 (L2)')
for m in ['qwen35','glm53','opus55','gpt61sol']:
    r=[e['rounds'] for k,e in B.items() if k[2]=='L2' and k[3]==m];print(m,st.mean(r),collections.Counter(r))
print('== per-app L2 pass, b1t32 / b1forced / b1fb for closed')
for run in ('b1t32','b1forced','b1fb'):
    R=B if run=='b1t32' else load(run)
    for m in ('opus55','gpt61sol'):
        print(run,m,' '.join(f"{a[:4]}:{100*st.mean(e['pass'] for k,e in R.items() if k[0]==a and k[2]=='L2' and k[3]==m):.0f}({sum(1 for k in R if k[0]==a and k[2]=='L2' and k[3]==m)})" if any(k[0]==a and k[2]=='L2' and k[3]==m for k in R) else f"{a[:4]}:-" for a in APPS))
print('== open pooled per app by level (12 open models), best open')
for lv in ('L2','L3'):
    print(lv,' '.join(f"{a[:4]}:{100*st.mean(e['pass'] for k,e in B.items() if k[0]==a and k[2]==lv and k[3] in OPEN):.1f}" for a in APPS))
print('== loose rule dE<=4 only, b1t32, per model pooled')
for lv in ('L2','L3'):
    v={m:100*st.mean(e['de00']<=4 for k,e in B.items() if k[2]==lv and k[3]==m) for m in OPEN+['opus55','gpt61sol']}
    print(lv,{m:round(x) for m,x in v.items()})
print('== per-round closeness (L2), forced vs fb')
for run in ('b1forced','b1fb'):
    R=load(run)
    for ms,name in ((OPEN,'open'),(['opus55'],'opus'),(['gpt61sol'],'gpt')):
        out=[]
        for lv in ('L2','L3'):
            eps=[(k,e) for k,e in R.items() if k[2]==lv and k[3] in ms and len(e.get('per_round',[]))==4]
            tot={}
            cl=[]
            for i in range(4):
                c=[]
                for k,e in eps:
                    b=B.get(k);de0=None
                    t=json.load(open(f"{D}/bench_b1_{k[0]}/tasks.jsonl")) if False else None
                    c.append(e['per_round'][i])
                cl.append(round(st.mean(c),2))
            out.append((lv,len(eps),cl))
        print(run,name,out)

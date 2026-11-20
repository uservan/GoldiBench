import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
# Qwen3.5 L2 ladder over 5 seeds (b1t32 = seed 0, b1t32_s1..s4): pass% "all" row per app, mean / sd over seeds.
import statistics as st
L=str(gbpaths.DATA)+'/logs'
apps=['darktable','rawtherapee','gimp','inkscape','blender']
models=['qwen35_0.8b','qwen35_2b','qwen35_4b','qwen35_9b','qwen35_27b','qwen35_35b_a3b','qwen35_122b_a10b','qwen35']
R={}  # (model,seed,app)->(pass,clo,n,fail)
for s in range(5):
    for a in apps:
        f=f'{L}/bench_b1_{a}_scores_b1t32{"" if s==0 else f"_s{s}"}.txt'
        for line in open(f):
            p=line.split()
            if len(p)>=8 and p[1]=='L2' and p[2]=='all' and p[0] in models:
                R[p[0],s,a]=(float(p[5]),float(p[8]),int(p[3]),int(p[4]))
print('model            seed0  s1   s2   s3   s4 | mean  sd  | per-app mean dt RT GIMP Ink Bl | clo mean | n/fail check')
for m in models:
    allp=[st.mean(R[m,s,a][0] for a in apps) for s in range(5)]
    clo=[st.mean(R[m,s,a][1] for a in apps) for s in range(5)]
    per=[st.mean(R[m,s,a][0] for s in range(5)) for a in apps]
    ns=sorted(set(R[m,s,a][2] for s in range(5) for a in apps)); fails=sum(R[m,s,a][3] for s in range(5) for a in apps)
    print(f'{m:16s} '+' '.join(f'{x:4.1f}' for x in allp)+f' | {st.mean(allp):4.1f} {st.stdev(allp):4.1f} | '+' '.join(f'{x:4.1f}' for x in per)+f' | {st.mean(clo):+.2f} | n={ns} fail={fails}')

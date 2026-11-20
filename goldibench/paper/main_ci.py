"""95% bootstrap intervals for Tab. main (2026-11-15): tasks resampled with replacement within each application (2000
draws), seeds averaged per task first, missing episodes as failures, the five applications weighing the same -- the same
estimate as main_tables.py. Output: logs/main_ci.json and a table on stdout (half-width of the interval, points)."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,os,random,statistics as st
from concurrent.futures import ThreadPoolExecutor
import main_tables as M
D=M.D;APPS=M.APPS;LEVELS=M.LEVELS;B=2000
def per_task_prog():
    T={}
    for a in APPS:
        tasks=[json.loads(l)['task_id'] for l in gbpaths.open_tasks(f'{D}/bench_b1_{a}/tasks.jsonl')]
        for r in ['b1t32']+[f'b1t32_s{s}' for s in range(1,5)]:
            f=f'{D}/bench_b1_{a}/runs/{r}/scores.json'
            if not os.path.exists(f):continue
            for e in json.load(open(f))['episodes']:T.setdefault((e['model'],e['level'],a),{}).setdefault(r,{})[e['task_id']]=bool(e['pass'])
        for k in [k for k in T if k[2]==a]:T[k]={'tasks':tasks,'runs':T[k]}
    return T
def per_task_gui():
    T={};ms={row[1] for row in M.GUI if row};jobs=[]
    for a in APPS:
        for r in ['b1g100_s0','b1g100_s1','b1g100_s2','b1g100_closed']:
            R=f'{D}/bench_b1_{a}_gui/runs/{r}'
            for d in os.listdir(R) if os.path.isdir(R) else []:
                t=d.split('_',2)
                if len(t)==3 and t[1] in LEVELS and t[2] in ms:jobs.append((a,r,t[2],t[1],t[0],f'{R}/{d}/episode.json'))
    with ThreadPoolExecutor(64) as ex:vals=list(ex.map(lambda j:M.read(j[5]),jobs))
    for (a,r,m,lv,tid,_),v in zip(jobs,vals):
        if v is not None:T.setdefault((m,lv,a),{}).setdefault(r,{})[tid]=v[0]
    for a in APPS:
        tasks={}
        for l in gbpaths.open_tasks(f'{D}/bench_b1_{a}_gui/tasks.jsonl'):
            t=json.loads(l);lv=t.get('level') or t['id'].split('_')[-1];tasks.setdefault(lv,[]).append(t['task_id'])
        for k in [k for k in T if k[2]==a]:T[k]={'tasks':tasks[k[1]],'runs':T[k]}
    return T
def ci(T,model,lv,rng):
    cells=[T.get((model,lv,a)) for a in APPS]
    if any(c is None for c in cells):return None
    vec=[[st.mean(run.get(t,False) for run in c['runs'].values()) for t in c['tasks']] for c in cells]
    pt=st.mean(100*st.mean(v) for v in vec)
    bs=sorted(st.mean(100*st.mean(rng.choices(v,k=len(v))) for v in vec) for _ in range(B))
    return pt,bs[int(.025*B)],bs[int(.975*B)]
def main():
    rng=random.Random(0);out={}
    for ch,rows,T in (('program',M.PROG,per_task_prog()),('gui',M.GUI,per_task_gui())):
        for row in rows:
            if not row:continue
            for lv in LEVELS:
                r=ci(T,row[1],lv,rng)
                if r:out[f'{ch}|{row[0]}|{lv}']=[round(x,2) for x in r]
    json.dump(out,open(f'{D}/logs/main_ci.json','w'),indent=1)
    hw={k:(v[2]-v[1])/2 for k,v in out.items()}
    for ch in ('program','gui'):
        print(ch,'max half-width by level:',{lv:round(max(h for k,h in hw.items() if k.startswith(ch) and k.endswith(lv)),1) for lv in LEVELS})
    for k in [k for k in out if 'GPT' in k or 'Opus' in k]:print(k,out[k])
if __name__=='__main__':main()

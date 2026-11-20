"""Freeze the B-1 sets (bench_b1_<app>): the last gate before any model run.

Refuses (exit 1, nothing written) if any accepted task lacks a check of gen_b1.py's gate list or has a check that failed,
has no revised intent, is missing from the independent re-check (verify_b1.py -> verify.json) or has a problem there,
if a task's files are missing, or if a step-count bucket is short of --per-k. With all checks passed it writes
<DATA>/bench_b1_final/{manifest.jsonl, split.json} (dev / test split, seeded, stratified by app x step count) and the
FROZEN marker in each set (sha256 of every task's program.json), but only with --approved: the user signs off the
validation report (report_b1.py) first. run_agent.py refuses a bench_b1_* set without FROZEN.

  python freeze_b1.py [--per-k 20] [--dev 0.2]            # check only
  python freeze_b1.py --per-k 20 --approved               # after the user approved the report
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,collections,hashlib,json,random,sys
from pathlib import Path
DATA=gbpaths.DATA
APPS=['darktable','gimp','rawtherapee','inkscape','blender']
REQUIRED=['C3_total','C2_repeat','C7_identity','V3','V2']   # + C4_necessary for k > 1

def problems(t,d,ver):
    out=[];c=t.get('checks',{})
    for k in REQUIRED+(['C4_necessary'] if t['steps']>1 else [])+(['CLIP'] if t['app']!='inkscape' else []):
        if k not in c:out.append(f'{k} missing');continue
        v=c[k]
        oks=[v['ok']] if 'ok' in v else [x['ok'] for x in v.values()]
        if not all(oks):out.append(f'{k} failed')
    if 'ssim_start_target' not in c:out.append('ssim missing')
    pl=c.get('plausible')
    if not pl:out.append('plausible missing')
    elif pl['status']=='rejected':out.append('plausible rejected')
    elif pl['status']!='ok' or not all(j.get('acceptable') is True for j in pl.get('judgments',[])) or len(pl.get('judgments',[]))<2:
        out.append('plausible: a judge did not accept (any reject drops the task, user decision 2026-11-01)')
    if not t.get('intent_draft'):out.append('intent not revised against the result')
    v=ver.get(t['task_id'])
    if v is None:out.append('not in verify.json (run verify_b1.py)')
    elif v['problems']:out.append('verify_b1: '+'; '.join(v['problems']))
    for f in ('start.png','target.png','program.json'):
        if not (d/f).exists():out.append(f'{f} missing')
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--per-k',type=int,default=20);ap.add_argument('--dev',type=float,default=0.2)
    ap.add_argument('--seed',type=int,default=0);ap.add_argument('--approved',action='store_true');ap.add_argument('--apps',nargs='+',default=APPS)
    a=ap.parse_args();bad=[];rows=[];short=[]
    for app in a.apps:
        s=DATA/f'bench_b1_{app}';ts=[json.loads(p.read_text()) for p in sorted((s/'tasks').glob('*/program.json'))]
        ver={r['task_id']:r for r in json.loads((s/'verify.json').read_text())} if (s/'verify.json').exists() else {}
        for t in ts:
            pr=problems(t,s/'tasks'/t['task_id'],ver)
            if pr:bad.append((app,t['task_id'],pr))
        by=collections.Counter(t['steps'] for t in ts)
        for k in range(1,6):
            if by[k]<a.per_k:short.append((app,k,by[k]))
        rows+=[{'app':app,'set':s.name,'task_id':t['task_id'],'steps':t['steps'],'kind':t['kind'],'generator':t['generator'],'modules':t['modules']} for t in ts]
    for x in bad:print('CHECK FAILED',*x)
    for app,k,n in short:print(f'SHORT {app} k={k}: {n} < {a.per_k}')
    if bad or short:print(f'refused: {len(bad)} tasks with failed / missing checks, {len(short)} short buckets');sys.exit(1)
    rng=random.Random(a.seed);g=collections.defaultdict(list)
    for r in rows:g[(r['app'],r['steps'])].append(r)
    for v in g.values():
        rng.shuffle(v);nd=round(a.dev*len(v))
        for i,r in enumerate(v):r['split']='dev' if i<nd else 'test'
    print(json.dumps({'tasks':len(rows),'dev':sum(r['split']=='dev' for r in rows),'test':sum(r['split']=='test' for r in rows)}))
    if not a.approved:print('all checks pass; not frozen (run again with --approved after the user signs off the report)');return
    out=DATA/'bench_b1_final';out.mkdir(exist_ok=True)
    (out/'manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    for app in a.apps:
        s=DATA/f'bench_b1_{app}'
        h={p.parent.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((s/'tasks').glob('*/program.json'))}
        (s/'FROZEN').write_text(json.dumps({'tasks':h},indent=1))
    print('frozen:',out/'manifest.jsonl')

if __name__=='__main__':main()

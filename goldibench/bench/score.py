"""Pilot scoring and task validation.

Score of an episode = the FINAL program re-rendered by us (never an agent-supplied image) against TARGET:
  de00       mean CIEDE2000 (<=1024 px renders)
  closeness  1 - de00(result,target) / de00(start,target)   (0 = no progress, 1 = exact; negative = moved away)
  pass       closeness >= 0.75 AND de00 <= 4 (make_pilot.passed; history there)
  auc        mean pass rate over thresholds 0.5, 1.0, ..., 10 (threshold-free summary)
Task validation: oracle replay must reproduce TARGET; x0.9 / x1.1 strength should pass; identity / half / over-strength
  must fail. Over-strength is x2, or x1.5 when x2 clips to the GUI range; null when both clip (the clipped program is then
  close to the oracle and passing it is no evidence of a lenient metric). x1.1 is null when it clips.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse,json,statistics as st,sys
import numpy as np
from PIL import Image
from skimage import color
sys.path.insert(0,str(Path(__file__).parent))
import ops
from make_pilot import NEUTRAL,OUT,MIN_CLOSE,MAX_DE,passed,scaled

THRESH=[0.5*i for i in range(1,21)]

def lab(p):return color.rgb2lab(np.asarray(Image.open(p).convert('RGB'),np.float32)/255)
def de(a,b):return float(color.deltaE_ciede2000(a,b).mean())

def validate(task,d):
    lt=lab(d/'target.png');res={'start':de(lab(d/'start.png'),lt)}
    over=scaled(task['program'],2.0)
    if over[1]:over=scaled(task['program'],1.5)
    for name,(prog,clipped) in [('oracle',(task['program'],False)),('near_0.9',scaled(task['program'],0.9)),('near_1.1',scaled(task['program'],1.1)),
                                ('half',scaled(task['program'],0.5)),('over',over)]:
        if clipped:res[name]=None;continue
        p=d/f'_val_{name}.png';ops.render(task['source_path'],prog,p);res[name]=de(lab(p),lt)
    return res

def _score_task(a):
    """Rows of every episode of one task (run in a worker process: the CIEDE2000 maps dominate scoring time)."""
    t,d,d0,runs=a;d=Path(d);runs=Path(runs);lt=lab(d/'target.png');rows=[]
    for ep in sorted((runs/t['task_id']).glob('L*_*/episode.json')):
        e=json.loads(ep.read_text());r=[x for x in e['rounds'] if 'program' in x]
        # No valid program at all: scored as unchanged START (closeness 0) and flagged, so failures stay visible.
        if any(x.get('error')=='render failed' for x in e['rounds']):r=[]   # its last program does not render: failed
        if not r:rows.append({**{k:e[k] for k in('task_id','level','model')},'kind':t['kind'],'de00':d0,'closeness':0.0,'rounds':0,'violations':0,
                              'pass':False,'failed':True,'modules_used':[],'modules_true':t['modules']});continue
        final=ep.parent/'final_rerender.png'   # rendered above
        if not final.exists():rows.append({**{k:e[k] for k in('task_id','level','model')},'kind':t['kind'],'de00':d0,'closeness':0.0,'rounds':len(r),'violations':0,
                              'pass':False,'failed':True,'rerender_failed':True,'modules_used':sorted(r[-1]['program']),'modules_true':t['modules']});continue
        dd=de(lab(final),lt)
        per=[de(lab(ep.parent/f"round{x['round']}.png"),lt) for x in r]
        rows.append({'task_id':e['task_id'],'level':e['level'],'model':e['model'],'kind':t['kind'],'de00':dd,'closeness':1-dd/d0,'pass':passed(dd,d0),
                     'rounds':len(r),'per_round':[round(x,2) for x in per],'violations':sum(len(x['violations']) for x in r),
                     'modules_used':sorted(r[-1]['program']),'modules_true':t['modules']})
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',default='v2',help="v1 = first pilot (episodes under tasks/)")
    ap.add_argument('--skip-validation',action='store_true');args=ap.parse_args()
    runs=OUT/'tasks' if args.run=='v1' else OUT/'runs'/args.run
    vf=OUT/'validation.json';val=json.loads(vf.read_text()) if vf.exists() else {}
    tasks=[json.loads(l) for l in gbpaths.open_tasks(OUT/'tasks.jsonl')];rows=[];jobs=[]
    # released PlayRaw set: 6 tasks whose forum thread states no licence ship without images or source (IMAGES_NOT_INCLUDED.txt)
    nosrc=[t['task_id'] for t in tasks if not t.get('source_path') or not (OUT/'tasks'/t['task_id']/'start.png').exists()]
    if nosrc:print(f'skipping {len(nosrc)} tasks released without images / source: {nosrc}',flush=True);tasks=[t for t in tasks if t['task_id'] not in nosrc]
    # B-1 sets were checked by verify_b1.py (a superset of this validation) before freezing; skip the 5 extra renders per task
    if OUT.name.startswith('bench_b1_'):args.skip_validation=True
    # final re-renders in parallel; one already newer than its episode is reused (rescoring after more models are added)
    import os
    from concurrent.futures import ThreadPoolExecutor
    # 2026-11-14: the scan reads every episode.json; serially on FSx it took ~1.5 min per task (hours per run), so the
    # tasks are scanned in parallel threads (same checks, same order of todo)
    def _scan(t):
        out=[]
        for ep in sorted((runs/t['task_id']).glob('L*_*/episode.json')):
            e=json.loads(ep.read_text());r=[x for x in e['rounds'] if 'program' in x]
            if any(x.get('error')=='render failed' for x in e['rounds']) or not r:continue
            f=ep.parent/'final_rerender.png'
            if not (f.exists() and f.stat().st_mtime>=ep.stat().st_mtime):out.append((t['source_path'],r[-1]['program'],f))
        return out
    with ThreadPoolExecutor(int(os.environ.get('SCAN_WORKERS','64'))) as ex:todo=[x for part in ex.map(_scan,tasks) for x in part]
    def _rr(a):   # a final program that does not re-render (e.g. darktable-cli timeout) is scored as failed, like 'render failed'
        try:ops.render(*a);return None
        except Exception as x:return f"{a[2]}\t{type(x).__name__}: {str(x)[-200:]}"
    with ThreadPoolExecutor(int(os.environ.get('SCORE_WORKERS','8'))) as ex:bad=[b for b in ex.map(_rr,todo) if b]
    if bad:(runs/'rerender_failures.txt').write_text('\n'.join(bad)+'\n');print(f'{len(bad)} final re-renders failed -> scored as failed, see {runs}/rerender_failures.txt')
    for t in tasks:
        d=OUT/'tasks'/t['task_id'];d0=de(lab(d/'start.png'),lab(d/'target.png'))
        if not args.skip_validation and 'over' not in val.get(t['task_id'],{}):val[t['task_id']]=validate(t,d)   # older caches lack near/over
        jobs.append((t,str(d),d0))
    with ProcessPoolExecutor(int(os.environ.get('SCORE_WORKERS','8'))) as ex:
        for part in ex.map(_score_task,[(t,dd,d0,str(runs)) for t,dd,d0 in jobs],chunksize=4):rows+=part
    if val:vf.write_text(json.dumps(val,indent=1))
    (runs/'scores.json').write_text(json.dumps({'validation':val,'episodes':rows},indent=1))
    if val:
        v=[val[t['task_id']] for t in tasks if t['task_id'] in val]
        def fr(k,f):
            a=[x for x in v if x[k] is not None];return f'{100*sum(not f(x[k],x["start"]) for x in a)/len(a):.0f}% of {len(a)}' if a else 'n/a'
        print('VALIDATION  oracle max dE %.3f | fail rate (should be 0): x0.9 %s  x1.1 %s | fail rate (should be 100%%): identity %s  half %s  over %s'%(
            max(x['oracle'] for x in v),fr('near_0.9',passed),fr('near_1.1',passed),fr('start',passed),fr('half',passed),fr('over',passed)))
    print(f"run {args.run}: {len(rows)} episodes, pass = closeness>={MIN_CLOSE} and dE<={MAX_DE}")
    print(f"{'model':7s} {'level':5s} {'kind':7s} {'n':>3s} {'fail':>4s} {'pass%':>6s} {'dE<=3%':>6s} {'auc':>5s} {'closeness':>9s} {'dE med':>7s} {'r1->final dE':>13s}")
    for m in sorted({r['model'] for r in rows}):
        for l in ['L1','L2','L3']:
            for k in ['single','multi','long','all']:
                s=[r for r in rows if r['model']==m and r['level']==l and (k=='all' or r['kind']==k)]
                if not s:continue
                first=[r['per_round'][0] for r in s if r.get('per_round')]
                print(f"{m:7s} {l:5s} {k:7s} {len(s):3d} {sum(r.get('failed',False) for r in s):4d} {100*sum(r['pass'] for r in s)/len(s):6.0f} {100*sum(r['de00']<=3 for r in s)/len(s):6.0f} "
                      f"{st.mean(st.mean(r['de00']<=t for r in s) for t in THRESH):5.2f} {st.mean(r['closeness'] for r in s):9.2f} "
                      f"{st.median(r['de00'] for r in s):7.2f} {st.median(first) if first else float('nan'):6.2f}->{st.median(r['de00'] for r in s):5.2f}")
if __name__=='__main__':main()

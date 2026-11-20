"""V-2 (docs/paper-plan.md §4): pass rate of the metric as a function of edit strength, per app.

Every task's hidden program is rescaled with make_pilot.scaled (each numeric field k times as far from neutral; hue
fields kept) for k in KS, rendered by the app, and scored against TARGET with the bench rule (closeness >= 0.75 and
mean CIEDE2000 <= 4). k = 1 is the oracle, k = 0 sets every field to neutral (the modules stay on), k = -1 reverses
every edit. Programs that the app's ranges clip are kept and flagged. Same app / set selection as make_pilot
(BENCH_APP, BENCH_SET). Output: <set>/magnitude_curve.json (per task and k) and the curve on stdout. Resumable.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,json,statistics as st,sys,tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import make_pilot as mp
import ops

KS=[-1,0,0.25,0.5,0.75,0.9,1,1.1,1.25,1.5,2,3]

def point(task,k,work):
    prog,clipped=mp.scaled(task['program'],k);d=mp.OUT/'tasks'/task['task_id']
    out=Path(work)/f"{task['task_id']}_{k}.png";ops.render(task['source_path'],prog,out)
    lt=mp.lab(d/'target.png');total=mp.de(mp.lab(d/'start.png'),lt);dd=mp.de(mp.lab(out),lt);out.unlink()
    return {'task_id':task['task_id'],'kind':task['kind'],'k':k,'clipped':clipped,'de':round(dd,3),
            'closeness':round(1-dd/total,3),'pass':mp.passed(dd,total)}

def safe(task,k,work):
    # one slow or failed render (darktable-cli timeouts under load, 2026-11-10) must not kill the run; the point is
    # left out of the JSON and picked up by the next (resumed) run
    try:return point(task,k,work)
    except Exception as e:print(f"skip {task['task_id']} k={k}: {type(e).__name__}",flush=True);return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=32);args=ap.parse_args()
    path=mp.OUT/'magnitude_curve.json';res=json.loads(path.read_text()) if path.exists() else []
    done={(r['task_id'],r['k']) for r in res}
    tasks=[json.loads(l) for l in gbpaths.open_tasks(mp.OUT/'tasks.jsonl')]
    jobs=[(t,k) for t in tasks for k in KS if (t['task_id'],k) not in done]
    with tempfile.TemporaryDirectory(dir=str(gbpaths.LOCAL)) as work,ThreadPoolExecutor(args.workers) as pool:
        for r in pool.map(lambda j:safe(*j,work),jobs):
            if r is None:continue
            res.append(r)
            if len(res)%50==0:path.write_text(json.dumps(res))
    path.write_text(json.dumps(res))
    print(f'{mp.OUT.name} ({ops.APP}): {len(tasks)} tasks; pass % / median closeness / clipped, by k')
    print('k       all            single         multi          clipped')
    for k in KS:
        rk=[r for r in res if r['k']==k]
        cell=lambda rs:f"{100*st.mean(r['pass'] for r in rs):3.0f} {st.median(r['closeness'] for r in rs):+6.2f}" if rs else ''
        print(f"{k:<6}  {cell(rk):14} {cell([r for r in rk if r['kind']=='single']):14} "
              f"{cell([r for r in rk if r['kind']=='multi']):14} {sum(r['clipped'] for r in rk)}")

if __name__=='__main__':main()

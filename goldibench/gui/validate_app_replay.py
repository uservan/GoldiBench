"""Oracle replay (C5) for the Inkscape / RawTherapee / Blender GUI benches: each task's hidden program is typed into the
GUI by the app's scripted replay (<app>_map.replay), then scored by the env exactly like an agent's episode.
Writes bench_b1_<app>_gui/replay_validation.json (task_id, pass, de00, closeness, gate, seconds).
Usage: BENCH_APP=<app> validate_app_replay.py [--tasks b000 ...] [--jobs 8]"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,importlib,json,os,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import app_envs
APP=os.environ['BENCH_APP'];M=importlib.import_module(f'{APP}_map')
DATA=gbpaths.DATA;OUT=DATA/f'bench_b1_{APP}_gui'

def one(task):
    t0=time.time();env=app_envs.ENVS[APP](OUT/'replay'/task['task_id']);shots=os.environ.get('REPLAY_SHOTS')
    try:
        env.reset(task)
        if APP=='blender':M.replay(env.d,task['program'],env.start_state)   # world rotation / camera position of START
        elif APP=='inkscape':M.replay(env.d,task['program'],env.d.image)   # page size of START (lengths are % of it)
        else:M.replay(env.d,task['program'])
        if shots:env.observe()['screenshot'].save(OUT/'replay'/task['task_id']/'after_replay.png')
        ev=env.evaluate()
    except Exception as e:ev={'pass':False,'gate':f'replay error {e!r}'[:300]}
    finally:env.close()
    r={'task_id':task['task_id'],'program':task['program'],**{k:ev.get(k) for k in ('pass','de00','closeness','gate','modules_used')},'seconds':round(time.time()-t0)}
    print(json.dumps(r),flush=True);return r

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--tasks',nargs='*');ap.add_argument('--jobs',type=int,default=8);ap.add_argument('--out',default='replay_validation.json');a=ap.parse_args()
    tasks=[json.loads(l) for l in gbpaths.open_tasks(OUT/'tasks.jsonl')];tasks=[t for t in tasks if t['level']=='L2' and (not a.tasks or t['task_id'] in a.tasks)]
    with ThreadPoolExecutor(a.jobs) as p:res=list(p.map(one,tasks))
    (OUT/a.out).write_text(json.dumps(res,indent=1))
    print(json.dumps({'tasks':len(res),'pass':sum(bool(r['pass']) for r in res)}))

if __name__=='__main__':main()

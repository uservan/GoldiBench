"""Open GUI-agent models on bench_gui1 through their published agents (osworld_agents.py); --manual gives HoloAgent the darktable manual as tools.

One step = one predict() call, as in OSWorld's lib_run_single; all actions it returns run before the next screenshot.
Episodes are written like run_gui_agent.py (runs/<run>/<task>_<model>/episode.json, step PNGs), so score_gui.py
scores them. A harness error writes harness_error.json instead and the episode is retried on resume.
BENCH_APP=gimp runs bench_gimp_gui1 (gimp_env.GimpEnv) instead. --seed sets the vLLM sampling seed of every request
(repeat runs for D-3 M-V5); it changes nothing for agents that decode greedily (OpenCUA: temperature 0).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,io,json,logging,os,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
APP=os.environ.get('BENCH_APP','darktable')
if APP=='gimp':
    from gimp_env import GimpEnv as Env
    from make_gimp_gui_tasks import OUT
elif APP in ('inkscape','rawtherapee','blender'):   # app_envs.py (2026-11-11)
    import app_envs
    Env=app_envs.ENVS[APP];OUT=gbpaths.DATA/os.environ.get('GUI_OUT',f'bench_b1_{APP}_gui')
else:
    from env import DarktableEnv as Env
    from make_gui_tasks import OUT
import osworld_agents as A

def png(img):
    b=io.BytesIO();img.save(b,'PNG');return b.getvalue()

def reachable(base):
    try:
        with urllib.request.urlopen(base+'/models',timeout=30) as r:return r.status==200
    except Exception:return False

# 2026-11-12: a run starting ~150 app instances at once (fresh HOME, START copy, app start-up on /shared) stalled the FSx
# and every node's screenshots timed out together (bursts of ~200 harness errors at each mass start); start-ups are gated.
import threading
KTEXT={}   # task_id -> knowledge text for L2 (GUI_KNOWLEDGE, filled in main)
START_GATE=threading.BoundedSemaphore(int(os.environ.get('GUI_START_CONC','8')))

def episode(name,task,args,base):
    run=OUT/'runs'/args.run/f"{task['id']}_{name}"
    if (run/'episode.json').exists():return   # 2026-11-15: done meanwhile by another process (helpers on other nodes)
    run.mkdir(parents=True,exist_ok=True)
    env=Env(run/'work');steps=[];end=None;t0=time.time()
    instr=task['instruction']+(f"\n[[TARGET_IMAGE:{task['target']}]]" if task['level']!='L1' else '')
    if task['task_id'] in KTEXT and task['level']=='L2':instr+='\n\n'+KTEXT[task['task_id']]   # GUI_KNOWLEDGE (see main)
    try:
        with START_GATE:obs=env.reset(task)   # at most GUI_START_CONC app start-ups at once per process
        agent=A.make_agent(name,base,args.max_steps,args.manual);agent.reset(logging.getLogger(f'agent.{name}'))
        for n in range(1,args.max_steps+1):
            try:res=agent.predict(instr,{'screenshot':png(obs['screenshot']),'accessibility_tree':None})
            except OSError:raise
            except Exception as e:
                # the official parser crashing on the model's reply (e.g. UI-TARS given a 3-number box) ends the
                # episode like an unparseable reply; anything while the server is down stays a harness error
                if not reachable(base):raise
                end='no valid reply';steps.append({'step':n,'response':f'agent error {e!r}'[:300],'actions':[],'errors':[]});break
            response,actions=res[0],list(res[1])
            if str(response).startswith('client error'):
                # UI-TARS returns this both when the server is down and when its parser fails 3 times on the model's
                # reply; OSWorld then ends the episode and evaluates it, so only an unreachable server is a harness error
                if not reachable(base):raise RuntimeError('agent could not reach the model')
                end='no valid reply';steps.append({'step':n,'response':str(response),'actions':[],'errors':[]});break
            errors=[];one=A.MODELS[name][0]=='prompt1a'   # gpt61gui1a: one GUI action per screenshot
            for a in actions:
                e,err=A.run_code(env,a,one=one);errors+=err
                if e:end=e;break
                if one:break   # later code blocks of the same reply are dropped too
            obs=env.observe();obs['screenshot'].save(run/f'step{n:03d}.png')
            steps.append({'step':n,'response':str(response)[-3000:],'actions':[str(a)[:500] for a in actions],'errors':errors})
            if end:break
        ev=env.evaluate()
    except Exception as e:
        ev={'pass':False,'gate':f'harness error {e!r}'[:300]};end='harness error'
    finally:
        env.close()
    rec={'id':task['id'],'task_id':task['task_id'],'level':task['level'],'kind':task['kind'],'model':name,'end':end or 'max steps',
         'n_steps':len(steps),'seconds':round(time.time()-t0),'eval':ev,'steps':steps}
    (run/('harness_error.json' if end=='harness error' else 'episode.json')).write_text(json.dumps(rec,indent=1))
    print(task['id'],name,rec['end'],ev.get('pass'),ev.get('de00'),ev.get('gate',''),flush=True)
    return rec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--models',nargs='+',default=list(A.MODELS));ap.add_argument('--levels',nargs='+',default=['L1','L2','L3'])
    ap.add_argument('--tasks',nargs='*');ap.add_argument('--run',default='o1');ap.add_argument('--max-steps',type=int,default=40)
    ap.add_argument('--concurrency',type=int,default=24);ap.add_argument('--seed',type=int)
    ap.add_argument('--manual',action='store_true',help='darktable manual as tools (HoloAgent only)');args=ap.parse_args()
    if args.manual:import manual;manual.use('gui')
    tasks=[json.loads(l) for l in gbpaths.open_tasks(OUT/'tasks.jsonl')]
    tasks=[t for t in tasks if t['level'] in args.levels and (not args.tasks or t['task_id'] in args.tasks)]
    # 2026-11-13: GUI_KNOWLEDGE=table_state_diff appends to every L2 instruction the same text the program channel's
    # --knowledge table_state_diff gives (knowledge.table_for of the program-channel task with the same task_id: what each
    # task tool does to START's image statistics, plus TARGET - START); needs BENCH_SET=bench_b1_<app> for knowledge.py
    if os.environ.get('GUI_KNOWLEDGE','').endswith('.json'):   # precomputed {task_id: text} (knowledge.py needs bs4 / skimage)
        KTEXT.update(json.load(open(os.environ['GUI_KNOWLEDGE'])))
        print(json.dumps({'knowledge':os.environ['GUI_KNOWLEDGE'],'tasks':len(KTEXT)}),flush=True)
    elif os.environ.get('GUI_KNOWLEDGE'):
        import knowledge
        pt={json.loads(l)['task_id']:json.loads(l) for l in gbpaths.open_tasks(knowledge.SET/'tasks.jsonl')}
        for t in tasks:
            if t['level']=='L2':KTEXT[t['task_id']]=knowledge.table_for(pt[t['task_id']],os.environ['GUI_KNOWLEDGE']=='table_state_diff')
        print(json.dumps({'knowledge':os.environ['GUI_KNOWLEDGE'],'tasks':len(KTEXT)}),flush=True)
    base={m:A.start_proxy(A.MODELS[m][1],args.seed) for m in args.models}
    jobs=[(m,t) for t in tasks for m in args.models if not (OUT/'runs'/args.run/f"{t['id']}_{m}"/'episode.json').exists()]
    # 2026-11-13: GUI_ONLY_EPISODES=<file of "<task id>_<model>" lines> restricts the run to exactly those episodes (re-running
    # harness errors on another node while the main run's agents still own the other episodes of the same tasks)
    if os.environ.get('GUI_ONLY_EPISODES'):
        keep={l.strip() for l in open(os.environ['GUI_ONLY_EPISODES']) if l.strip()}
        jobs=[(m,t) for m,t in jobs if f"{t['id']}_{m}" in keep]
    # 2026-11-12: one pool per model. With one shared pool the episodes of the slowest (saturated) servers piled up in
    # every slot and the other models' servers idled (Qwen 27B / 122B at 0 requests while 397B / 9B queued 70 each).
    # Per-model size: --concurrency / number of models (at least 2), overridable by GUI_MODEL_CONC='{"model": n, ...}'.
    over=json.loads(os.environ.get('GUI_MODEL_CONC') or '{}')
    share=max(2,args.concurrency//max(1,len(args.models)))
    pools={m:ThreadPoolExecutor(int(over.get(m,share))) for m in args.models}
    futs=[pools[m].submit(episode,m,t,args,base[m]) for m,t in jobs]
    for f in futs:f.result()
    for p in pools.values():p.shutdown()
    print(json.dumps({'episodes':len(jobs)}))

if __name__=='__main__':main()

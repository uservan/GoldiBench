"""GUI task sets for Inkscape, RawTherapee and Blender (bench_b1_<app>_gui), as make_gimp_gui_tasks.py does for GIMP:
every frozen B-1 task (same hidden program, START, TARGET, pass rule) as OSWorld-style task configs for app_envs.py.
L2 names the task's tools (gate: no other tool), L3 gives the target only (any tool). L1 states every value in GUI
terms; it needs the field map of each app (GUI label + display value), so L1 is written only once that map exists
(LEVELS defaults to L2 L3). Usage: BENCH_APP=<app> make_app_gui_tasks.py"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent/'bench'));sys.path.insert(0,str(Path(__file__).parent))
DATA=gbpaths.DATA
APP=os.environ['BENCH_APP'];SRC=DATA/f'bench_b1_{APP}';OUT=DATA/f'bench_b1_{APP}_gui'
import importlib;O=importlib.import_module(f'ops_{APP}')
OPEN={'inkscape':'Inkscape is open on the drawing to edit (START). ','rawtherapee':'RawTherapee is open in the editor on the photo to edit (START). ',
      'blender':'Blender is open on the scene to edit (START); the result is the scene rendered from its camera. '}[APP]
DROP={'inkscape':{'b112':'START copy does not render identically to the source (inkscape_start.check)'}}.get(APP,{})

STATE={}
def start_state(t):
    """Blender: START's world rotation / camera position (blender_state.py on the GUI copy), which L1 values depend on."""
    if t['task_id'] not in STATE:
        import app_envs,blender_start,tempfile,shutil
        cache=app_envs.OB.LOCAL/'apps/gui_agents/blender_start_cache'/Path(t['source_path']).name
        if not cache.exists():cache.parent.mkdir(parents=True,exist_ok=True);blender_start.gui_copy(t['source_path'],cache)
        STATE[t['task_id']]=app_envs.blender_state(cache)
    return STATE[t['task_id']]

def l1_text(t):
    M=importlib.import_module(f'{APP}_map')   # GUI names and display values (<app>_map.py, checked by the oracle replay)
    extra={'inkscape':lambda:(t['source_path'],),'blender':lambda:(start_state(t),)}.get(APP,lambda:())()
    return OPEN+f'Apply these {O.PRODUCT} tools with exactly these settings: '+'; '.join(M.l1_text(t['program'],*extra))+'.'

def config(t,level):
    d=SRC/'tasks'/t['task_id'];names=', '.join(O.OPS[m][0] for m in t['modules'])
    goal='Edit it so that it matches the TARGET image as closely as possible'+(' when rendered' if APP=='blender' else '')+'. '
    if level=='L1':instr=l1_text(t)
    else:instr=OPEN+goal+(f'Use only these {O.PRODUCT} tools: {names}.' if level=='L2' else f'Any {O.PRODUCT} tool may be used.')
    return {'id':f"{t['task_id']}_{level}",'snapshot':APP,'instruction':instr,'source':t['source'],
            'config':[{'type':'open_image','parameters':{'path':t['source_path']}}],'related_apps':[APP],'level':level,
            'task_id':t['task_id'],'kind':t['kind'],'allowed_modules':t['modules'] if level in ('L1','L2') else None,
            'program':t['program'],'target':str(d/'target.png'),
            'evaluator':{'func':f'{APP}_target_match','expected':{'type':'image','path':str(d/'target.png')},'start_path':str(d/'start.png'),
                         'options':{'min_closeness':0.75,'max_de00':4.0}}}

def main():
    levels=os.environ.get('LEVELS','L2 L3').split()
    tasks=[json.loads(l) for l in gbpaths.open_tasks(SRC/'tasks.jsonl')];(OUT/'tasks').mkdir(parents=True,exist_ok=True)
    drop=dict(DROP);val=OUT/'replay_validation.json'
    if APP=='inkscape':   # user 2026-11-11 (option A): the Filter Editor keeps 3 decimals of the turbulence frequency, so a
        # roughen target cannot be reproduced in the GUI (best replay dE 3.2); dropped like darktable / GIMP drop unreachable tasks
        drop.update({t['task_id']:'roughen: turbulence frequency not settable to the program value in the GUI (3 decimals)'
                     for t in tasks if 'roughen' in t['program'] and t['task_id'] not in drop})
    if val.exists():   # tasks the scripted GUI replay could not reproduce are dropped (C5), as for darktable / GIMP
        drop.update({r['task_id']:f"replay dE {r.get('de00')}, gate {r.get('gate')}" for r in json.loads(val.read_text()) if not r.get('pass')})
    (OUT/'rejected.json').write_text(json.dumps(drop,indent=1));tasks=[t for t in tasks if t['task_id'] not in drop]
    if APP=='blender' and 'L1' in levels:   # START states up front, in parallel (one background Blender each)
        from concurrent.futures import ThreadPoolExecutor
        list(ThreadPoolExecutor(12).map(start_state,tasks))
    with open(OUT/'tasks.jsonl','w') as h:
        for t in tasks:
            for level in levels:
                c=config(t,level);(OUT/'tasks'/f"{c['id']}.json").write_text(json.dumps(c,indent=1));h.write(json.dumps(c)+'\n')
    print(json.dumps({'app':APP,'tasks':len(tasks),'levels':levels,'configs':len(levels)*len(tasks)}))

if __name__=='__main__':main()

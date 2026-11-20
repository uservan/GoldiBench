"""GUI task set bench_gui1: the bench_pilot2 tasks whose modules are all reachable in the darktable GUI (gui_map.GUI),
as OSWorld-style task configs, one per (task, level). Same hidden program, START, TARGET and pass criterion as the
program bench, so GUI and program results compare task by task.

TARGETs are re-rendered here with darktable's real module defaults (dt_params symbolic-$DEFAULT fix: shadows and
highlights now uses the bilateral filter, as the GUI does; bench_pilot2 targets keep the old rendering) and every task
re-passes make_pilot's acceptance checks (dE range, every module visible, half fails, x0.9 passes); rejects are dropped.
L1 lists every field to set, in GUI labels and display units, including fields whose GUI default differs from the
program's neutral value (ops.FIXED: shadows and highlights starts at +50/-50, split-toning saturations at 0.5).
L2 names the modules (gate: no other module may be used). L3 gives the target only (any darktable module allowed).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import gui_map as G,ops,dt_params
from replay import fmt
from make_pilot import accept
dt_params.LEGACY_SYMBOLS=False   # importing make_pilot may switch it on (BENCH_SET); bench_gui1 renders with real defaults

DATA=gbpaths.DATA
import os
# GUI_SRC / GUI_OUT pick another program set. A frozen B-1 set (bench_b1_*) keeps its own TARGETs (copied, never re-rendered);
# whether the GUI reproduces them is the replay check's job (validate_replay.py), whose failures a rebuild drops.
SRC=DATA/os.environ.get('GUI_SRC','bench_pilot2');OUT=DATA/os.environ.get('GUI_OUT','bench_gui1')
FROZEN_SRC=SRC.name.startswith('bench_b1_')
OPEN=('darktable is open in the darkroom on the photo to edit (START). ')

def gui_fields(program):
    """{module: {field: program value}} including FIXED fields, in gui_map order."""
    out={}
    for m,p in program.items():
        full={**ops.FIXED.get(m,{}),**p};out[m]={f:full[f] for f in G.GUI[m][1] if f in full}
    return out

def l1_text(program):
    parts=[]
    for m,p in gui_fields(program).items():
        fs=', '.join(f'{G.label(m,f)} = '+(G.display(m,f,v) if (m,f) in G.COMBO else f'{fmt(round(G.display(m,f,v),3))}{G.UNIT.get((m,f),"")}') for f,v in p.items())
        parts.append(f'{G.GUI[m][0]}: {fs}')
    return OPEN+'Apply these darktable modules with exactly these settings: '+'; '.join(parts)+'.'

def config(t,level):
    d=OUT/'tasks'/t['task_id']
    if level=='L1':instr=l1_text(t['program'])
    elif level=='L2':instr=OPEN+('Edit it so that it matches the TARGET image as closely as possible. Use only these darktable modules: '
                                 +', '.join(G.GUI[m][0] for m in t['modules'])+'.')
    else:instr=OPEN+'Edit it so that it matches the TARGET image as closely as possible. Any darktable module may be used.'
    return {'id':f"{t['task_id']}_{level}",'snapshot':'darktable-5.6.2','instruction':instr,'source':t['source'],
            'config':[{'type':'open_image','parameters':{'path':t['source_path']}}],
            'related_apps':['darktable'],'level':level,'task_id':t['task_id'],'kind':t['kind'],
            'allowed_modules':t['modules'] if level in('L1','L2') else None,
            'program':t['program'],'gui_program':gui_fields(t['program']),
            'target':str(d/'target.png'),
            'evaluator':{'func':'darktable_target_match','result':{'type':'darktable_xmp'},
                         'expected':{'type':'image','path':str(d/'target.png')},'start_path':str(d/'start.png'),
                         'options':{'min_closeness':0.75,'max_de00':4.0}}}

def main():
    tasks=[json.loads(l) for l in gbpaths.open_tasks(SRC/'tasks.jsonl')]
    keep=[];rejected={}
    val=OUT/'replay_validation.json';replay_bad={}
    if FROZEN_SRC and val.exists():replay_bad={r['task_id']:(r.get('gate') or f"replay dE {r.get('de00')}, closeness {r.get('closeness')}") for r in json.loads(val.read_text()) if not r.get('pass')}
    unreachable={t['task_id']:sorted(set(t['modules'])-set(G.GUI)) for t in tasks if not set(t['modules'])<=set(G.GUI)}
    if FROZEN_SRC:(OUT/'unreachable.json').parent.mkdir(parents=True,exist_ok=True);(OUT/'unreachable.json').write_text(json.dumps(unreachable,indent=1))
    for t in tasks:
        if not set(t['modules'])<=set(G.GUI):continue
        d=OUT/'tasks'/t['task_id'];d.mkdir(parents=True,exist_ok=True);shutil.copy(SRC/'tasks'/t['task_id']/'start.png',d/'start.png')
        if FROZEN_SRC:
            if t['task_id'] in replay_bad:rejected[t['task_id']]=replay_bad[t['task_id']];continue
            shutil.copy(SRC/'tasks'/t['task_id']/'target.png',d/'target.png');keep.append(t);continue
        total,status=accept(t['source_path'],t['program'],d,t['task_id'])
        if total is None:rejected[t['task_id']]=status;continue
        keep.append({**t,'start_target_de00':round(total,2)})
    (OUT/'rejected.json').write_text(json.dumps(rejected,indent=1))
    with open(OUT/'tasks.jsonl','w') as h:
        for t in keep:
            for level in('L1','L2','L3'):
                c=config(t,level);(OUT/'tasks'/f"{c['id']}.json").write_text(json.dumps(c,indent=1));h.write(json.dumps(c)+'\n')
    print(json.dumps({'tasks':len(keep),'of':len(tasks),'rejected':rejected,'single':sum(t['kind']=='single' for t in keep),
                      'multi':sum(t['kind']=='multi' for t in keep),'configs':3*len(keep)}))

if __name__=='__main__':main()

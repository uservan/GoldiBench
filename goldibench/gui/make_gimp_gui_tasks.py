"""GUI task set bench_gimp_gui1: every bench_gimp1 task as OSWorld-style task configs for the GIMP GUI (gimp_env.py), one
per (task, level). Same hidden program, START, TARGET and pass criterion as the program bench, so GUI and program results
compare task by task. gimp_calibrate.py found no property where the GUI's filter defaults differ from the renderer's.
The GUI keeps filters as a non-destructive stack, the program renderer merges each one; the oracle replay
(gimp_validate_replay.py) measures what that leaves: the hidden program typed into the GUI must still pass. Once
replay_validation.json exists, a rebuild drops the tasks whose replay failed (rejected.json), as bench_gui1 drops tasks
the darktable GUI cannot reproduce.

L1 lists every field to set in GUI labels and display units, rounded to the decimals the dialog keeps (gimp_map), plus
FIXED fields; L2 names the filters (gate:
no other layer filter may be used); L3 gives the target only (any GIMP filter or tool).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import gimp_map as G,ops_gimp
from gimp_replay import fmt

DATA=gbpaths.DATA
import os
# GUI_SRC / GUI_OUT pick another program set (B-1: GUI_SRC=bench_b1_gimp GUI_OUT=bench_b1_gimp_gui); TARGETs are the set's own
SRC=DATA/os.environ.get('GUI_SRC','bench_b1_gimp');OUT=DATA/os.environ.get('GUI_OUT','bench_b1_gimp_gui')   # the paper's sets
OPEN='GIMP is open on the photo to edit (START). '

def menu(tool):return ops_gimp.OPS[tool][0]

def gui_fields(program):
    """{tool: {field: program value}} with FIXED fields, in gimp_map order."""
    out={}
    for m,p in program.items():
        full={**ops_gimp.FIXED.get(m,{}),**p};out[m]={f:full[f] for f in G.FIELDS[m][0] if f in full}
    return out

def l1_text(program):
    parts=[]
    for m,p in gui_fields(program).items():
        fs=', '.join(f'{G.FIELDS[m][0][f][0]} = {fmt(G.shown(m,f,v),3)}' for f,v in p.items())
        parts.append(f'{menu(m)}: {fs}')
    return OPEN+'Apply these GIMP filters in this order, each once, with exactly these settings: '+'; '.join(parts)+'.'

def config(t,level):
    d=SRC/'tasks'/t['task_id']
    names=', '.join(menu(m) for m in t['modules'])
    if level=='L1':instr=l1_text(t['program'])
    elif level=='L2':instr=OPEN+'Edit it so that it matches the TARGET image as closely as possible. Use only these GIMP filters: '+names+'.'
    else:instr=OPEN+'Edit it so that it matches the TARGET image as closely as possible. Any GIMP filter or tool may be used.'
    return {'id':f"{t['task_id']}_{level}",'snapshot':'gimp-3.2.6','instruction':instr,'source':t['source'],
            'config':[{'type':'open_image','parameters':{'path':t['source_path']}}],
            'related_apps':['gimp'],'level':level,'task_id':t['task_id'],'kind':t['kind'],
            'allowed_modules':t['modules'] if level in('L1','L2') else None,
            'program':t['program'],'gui_program':gui_fields(t['program']),'target':str(d/'target.png'),
            'evaluator':{'func':'gimp_target_match','result':{'type':'gimp_xcf'},
                         'expected':{'type':'image','path':str(d/'target.png')},'start_path':str(d/'start.png'),
                         'options':{'min_closeness':0.75,'max_de00':4.0}}}

def main():
    tasks=[json.loads(l) for l in gbpaths.open_tasks(SRC/'tasks.jsonl')];(OUT/'tasks').mkdir(parents=True,exist_ok=True)
    val=OUT/'replay_validation.json'
    if val.exists():
        bad={r['task_id']:(r.get('gate') or f"replay dE {r.get('de00')}, closeness {r.get('closeness')}") for r in json.loads(val.read_text()) if not r.get('pass')}
        (OUT/'rejected.json').write_text(json.dumps(bad,indent=1));tasks=[t for t in tasks if t['task_id'] not in bad]
    with open(OUT/'tasks.jsonl','w') as h:
        for t in tasks:
            for level in('L1','L2','L3'):
                c=config(t,level);(OUT/'tasks'/f"{c['id']}.json").write_text(json.dumps(c,indent=1));h.write(json.dumps(c)+'\n')
    print(json.dumps({'tasks':len(tasks),'single':sum(t['kind']=='single' for t in tasks),'multi':sum(t['kind']=='multi' for t in tasks),
                      'configs':3*len(tasks)}))

if __name__=='__main__':main()

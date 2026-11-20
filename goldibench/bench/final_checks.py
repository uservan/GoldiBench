"""Testability checks C2 / C4 and metric check V-3 (docs/paper-plan.md §3 C, §4 D-2) on the final test set, one set at
a time (BENCH_APP / BENCH_SET as make_pilot; only the set's tasks in bench_final/manifest.jsonl).

  C2  deterministic render: the hidden program rendered now vs the stored TARGET (rendered when the set was made):
      max per-pixel |RGB| difference and mean CIEDE2000
  C4  no redundant step (multi-step tasks): the program with one module dropped, for every module; the step is
      redundant if the result still passes against TARGET. dE of the dropped render to TARGET is kept.
  V-3 wrong solutions that never use the app, scored with the bench rule: START shifted to TARGET's mean L*a*b*
      ("one global colour correction"), and Reinhard transfer (TARGET's per-channel L*a*b* mean and std). Identity and
      the reversed edit are V-2's k = 0 / -1.
Output: bench_final/checks/<set>.json. Resumable per task.

  BENCH_APP=gimp BENCH_SET=bench_gimp1 python final_checks.py [--workers 8]
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,json,tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image
from skimage import color
import make_pilot as mp
import ops

def rgb(p):return np.asarray(Image.open(p).convert('RGB'),np.int16)

def v3(start,target):
    ls,lt=mp.lab(start),mp.lab(target);d0=mp.de(ls,lt);res={}
    for name,cand in [('mean_shift',ls+(lt.mean((0,1))-ls.mean((0,1)))),
                      ('reinhard',(ls-ls.mean((0,1)))/(ls.std((0,1))+1e-6)*lt.std((0,1))+lt.mean((0,1)))]:
        cand=color.rgb2lab(np.clip(color.lab2rgb(cand),0,1))   # back through sRGB, as a real edit would be stored
        dd=mp.de(cand,lt);res[name]={'de':round(dd,3),'closeness':round(1-dd/d0,3),'pass':mp.passed(dd,d0)}
    return res

def check(t,work):
    d=mp.OUT/'tasks'/t['task_id'];tgt=d/'target.png';lt=mp.lab(tgt);d0=mp.de(mp.lab(d/'start.png'),lt)
    out=Path(work)/f"{t['task_id']}_c2.png";ops.render(t['source_path'],t['program'],out)
    r={'task_id':t['task_id'],'kind':t['kind'],'steps':len(t['program']),
       'c2':{'max_px':int(np.abs(rgb(out)-rgb(tgt)).max()),'de':round(mp.de(mp.lab(out),lt),4)},'v3':v3(d/'start.png',tgt)}
    if len(t['program'])>1:
        r['c4']={}
        for m in t['program']:
            p=Path(work)/f"{t['task_id']}_drop_{m}.png";ops.render(t['source_path'],{k:v for k,v in t['program'].items() if k!=m},p)
            dd=mp.de(mp.lab(p),lt);r['c4'][m]={'de':round(dd,3),'redundant':mp.passed(dd,d0)};p.unlink()
    out.unlink();return r

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=8);args=ap.parse_args()
    ids={x['task_id'] for x in map(json.loads,open(mp.DATA/'bench_final'/'manifest.jsonl')) if x['set']==mp.OUT.name}
    tasks=[t for t in map(json.loads,gbpaths.open_tasks(mp.OUT/'tasks.jsonl')) if t['task_id'] in ids]
    f=mp.DATA/'bench_final'/'checks'/f'{mp.OUT.name}.json';f.parent.mkdir(exist_ok=True)
    done={r['task_id']:r for r in json.loads(f.read_text())} if f.exists() else {}
    todo=[t for t in tasks if t['task_id'] not in done]
    with tempfile.TemporaryDirectory() as work,ThreadPoolExecutor(args.workers) as ex:
        for r in ex.map(lambda t:check(t,work),todo):
            done[r['task_id']]=r;f.write_text(json.dumps(list(done.values()),indent=1))
    rs=list(done.values());c4=[v for r in rs for v in r.get('c4',{}).values()]
    print(f"{mp.OUT.name}: {len(rs)} tasks | C2 max px diff {max(r['c2']['max_px'] for r in rs)}, max dE {max(r['c2']['de'] for r in rs)}"
          f" | C4 redundant steps {sum(v['redundant'] for v in c4)}/{len(c4)}"
          f" | V-3 pass mean_shift {sum(r['v3']['mean_shift']['pass'] for r in rs)}, reinhard {sum(r['v3']['reinhard']['pass'] for r in rs)} of {len(rs)}")

if __name__=='__main__':main()

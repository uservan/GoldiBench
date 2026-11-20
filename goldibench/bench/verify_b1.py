"""Independent re-check of accepted B-1 tasks (layers 2 and 3 of the validation; layer 1 = tests/test_b1_gates.py,
layer 4 = visual review). Nothing is taken from gen_b1.py's stored numbers: every task is re-rendered here from its
program.json and every gate is recomputed; the stored numbers are only compared against.

Layer 2, recomputed (criteria as in gen_b1.py):
  TARGET reproduced     fresh render vs stored target.png: dE <= 0.05
  C3                    START->TARGET dE in range
  C4                    without any one step the task fails the pass rule
  V-2                   x0.9 / x1.1 pass (unless clipped), x0.5 / x1.5 fail
  V-3                   mean-shift and Reinhard fail
  stored vs recomputed  |difference| <= 0.05 dE for every stored number
Layer 3, anomalies:
  image                 START / TARGET / step images exist, same size, not blank (std > 2), CLIP recomputed: blown
                        (L* > 97) and crushed (L* < 5) area each grow by at most 10 points START -> TARGET (a problem for
                        photo apps and Blender, a warning for Inkscape); the intent was revised against the result
  text                  L1 instruction contains every program value; the L2 tool list equals the program's tools;
                        the intent names no tool of the library and contains no digits;
                        intent and every reason are complete sentences without broken characters
  provenance            generator and manual pages recorded; source asset recorded
Output: <DATA>/bench_b1_<app>/verify.json and a summary per app on stdout; exit 1 if any task has a problem.

  BENCH_APP=gimp python verify_b1.py
"""
from concurrent.futures import ThreadPoolExecutor
import json,os,re,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
APP=os.environ.get('BENCH_APP','darktable');os.environ.setdefault('BENCH_SET',f'bench_b1_{APP}')
import make_pilot as mp, ops
from final_checks import v3

def arr(p):return np.asarray(Image.open(p).convert('RGB'),np.int16)

def verify(t,d,work):
    pr=[];src=t['source_path'];prog=t['program'];k=len(prog);r={'task_id':t['task_id']}
    st,tg=d/'start.png',d/'target.png'
    if not st.exists() or not tg.exists():return {**r,'problems':['start/target missing']}
    ls,lt=mp.lab(st),mp.lab(tg);d0=mp.de(ls,lt);r['d0']=round(d0,3)
    fresh=Path(work)/'fresh.png';ops.render(src,prog,fresh);e=mp.de(mp.lab(fresh),lt);r['target_repro']=round(e,4)
    if e>0.05:pr.append(f'TARGET not reproduced (dE {e:.3f})')
    lo,hi=(6.0,45.0 if k>=5 else 30.0)
    if k==1:lo=ops.MIN_DE_LOCAL.get(next(iter(prog)),lo)
    if not lo<=d0<=hi:pr.append(f'C3 dE {d0:.2f} outside [{lo},{hi}]')
    def cmp(name,mine,stored):
        if stored is not None and abs(mine-stored)>0.05:pr.append(f'{name}: recomputed {mine:.3f} vs stored {stored:.3f}')
    cmp('C3 total',d0,t['checks']['C3_total']['de'])
    if k>1:
        for m in prog:
            p=Path(work)/f'drop.png';ops.render(src,{x:v for x,v in prog.items() if x!=m},p);e=mp.de(mp.lab(p),lt)
            if mp.passed(e,d0):pr.append(f'C4 {m} unnecessary (dE {e:.2f})')
            cmp(f'C4 {m}',e,t['checks'].get('C4_necessary',{}).get(m,{}).get('de'))
    for f,want in ((0.9,True),(1.1,True),(0.5,False),(1.5,False)):
        p,cl=mp.scaled(prog,f)
        if want and cl:continue
        q=Path(work)/'scaled.png';ops.render(src,p,q);e=mp.de(mp.lab(q),lt)
        if mp.passed(e,d0)!=want:pr.append(f'V-2 x{f} {"fails" if want else "passes"} (dE {e:.2f})')
        cmp(f'V-2 x{f}',e,t['checks'].get('V2',{}).get(str(f),{}).get('de'))
    for n,x in v3(st,tg).items():
        if x['pass']:pr.append(f'V-3 {n} passes')
    # layer 3: images
    a,b=arr(st),arr(tg)
    if a.shape!=b.shape:pr.append(f'size START {a.shape} != TARGET {b.shape}')
    for n,x in (('START',a),('TARGET',b)):
        if x.std()<=2:pr.append(f'{n} blank')
    r['warnings']=[]
    L0,L1=ls[...,0],lt[...,0]
    for n,f in (('blown',lambda L:float((L>97).mean())),('crushed',lambda L:float((L<5).mean()))):
        a0,a1=f(L0),f(L1);r[n]=[round(a0,4),round(a1,4)]
        if a1-a0>0.10:(pr if APP!='inkscape' else r['warnings']).append(f'CLIP {n} area grows {100*a0:.0f}% -> {100*a1:.0f}%')
        cmp(f'CLIP {n} START',100*a0,None if 'CLIP' not in t['checks'] else 100*t['checks']['CLIP'][n][0])
        cmp(f'CLIP {n} TARGET',100*a1,None if 'CLIP' not in t['checks'] else 100*t['checks']['CLIP'][n][1])
    if APP!='inkscape' and 'CLIP' not in t['checks']:pr.append('CLIP gate not run in generation')
    if not t.get('intent_draft'):pr.append('intent not revised against the result (no intent_draft)')
    for j in range(1,k):
        if not (d/f'step{j}.png').exists():pr.append(f'step{j}.png missing')
    # layer 3: text
    l1=t['l1_instruction']
    for m,p in prog.items():
        if ops.OPS[m][0] not in l1 and m not in l1:pr.append(f'L1 misses {m}')
        for f,v in p.items():
            if f'{f} = {v}' not in l1:pr.append(f'L1 misses {m}.{f}')
    if sorted(t['modules'])!=sorted(prog):pr.append('L2 tool list != program tools')
    intent=t.get('intent') or ''
    names={m.lower() for m in ops.OPS}|{ops.OPS[m][0].lower() for m in ops.OPS}
    leak=[n for n in names if len(n)>3 and re.search(r'\b'+re.escape(n.replace('_',' '))+r'\b',intent.lower().replace('_',' '))]
    if leak:pr.append(f'intent names tools: {leak}')
    if re.search(r'\d',intent):pr.append('intent has digits')
    if len(re.findall(r'[A-Za-z]{2,}',intent))<6:pr.append('intent has fewer than 6 words')
    for n,x in [('intent',intent)]+[(f'reason {m}',r or '') for m,r in t.get('reasons',{}).items()]:
        x=x.strip().rstrip('"\')')
        if not x.endswith(('.','!','?')) or '\ufffd' in x:pr.append(f'{n} incomplete / broken text')
    # round 3 review (2026-11-01): revised intents claimed a darkened/brightened frame with no vignette step, and reasons
    # leaked revision feedback; written out here again, not imported from gen_b1, so the check stays independent
    if not any('vignet' in (m+' '+ops.OPS[m][0]).lower() for m in prog):
        fw=re.findall(r'\b(?:borders?|corners?|vignett\w*|framed|framing|(?:darken|brighten|lighten)\w*\s+(?:\w+\s+)?(?:frame|edges?))\b',intent,re.I)
        if fw:pr.append(f'intent mentions a frame/vignette but no vignette step: {fw}')
    if 'reasons_draft' not in t:pr.append('reasons not revised against the result (no reasons_draft)')
    for m,x in t.get('reasons',{}).items():
        w=re.search(r'\b(replac\w*|previous\w*|earlier|attempt\w*|feedback|reviewers?|flagged|instead of the|distinct(ly)? from)\b',x or '',re.I)
        if w:pr.append(f'reason {m} talks about the editing process ("{w.group(0)}")')
        # 2026-11-02 review (rawtherapee b085, darktable b043): a revised reason quoted the generator's measurements
        n=re.search(r'\d+(\.\d+)?\s*(L\*|dE|%)',x or '')
        if n:pr.append(f'reason {m} quotes a measurement ("{n.group(0)}")')
    for f in ('generator','manual_pages','source'):
        if not t.get(f):pr.append(f'{f} not recorded')
    return {**r,'problems':pr}

def main():
    ts=[json.loads(p.read_text()) for p in sorted((mp.OUT/'tasks').glob('*/program.json'))]
    with tempfile.TemporaryDirectory(dir=os.environ.get('VE_TMP')) as w:
        def one(t):
            d=Path(w)/t['task_id'];d.mkdir()
            try:r=verify(t,mp.OUT/'tasks'/t['task_id'],d)
            except Exception as e:r={'task_id':t['task_id'],'problems':[f'verify error {type(e).__name__}: {e}'[:200]]}
            print(t['task_id'],r['problems'] or 'ok',('warn: '+'; '.join(r['warnings'])) if r.get('warnings') else '',flush=True)
            return r
        # VERIFY_WORKERS>1 checks tasks concurrently (renders are subprocesses); results keep task order
        with ThreadPoolExecutor(int(os.environ.get('VERIFY_WORKERS','1'))) as ex:res=list(ex.map(one,ts))
    (mp.OUT/'verify.json').write_text(json.dumps(res,indent=1))
    bad=[r for r in res if r['problems']]
    print(f'{APP}: {len(res)} tasks re-checked, {len(bad)} with problems')
    sys.exit(1 if bad else 0)

if __name__=='__main__':main()

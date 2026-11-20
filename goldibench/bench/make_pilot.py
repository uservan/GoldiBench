"""Pilot task set (knowledge channel). Each task: a source photo, a hidden program {module: {field: value}},
START = darktable render with no edits, TARGET = darktable render of the program, both at <=1024 px.

  single-step: one module, fields sampled away from neutral (programmatic, even module coverage)
  long:        5-7 modules (capped by the app's module count), same as multi; START->TARGET up to MAX_TOTAL_LONG
  multi-step:  2-4 modules, the set drawn so every module is used about equally (v1 let the VLM choose and never
               picked colisa or shadhi); an open VLM looking at the photo sets the values (a "professional edit")
Filters: START->TARGET mean CIEDE2000 in [MIN_DE, 30] (v1 used 3: on 3.5-5 tasks another module alone reached dE<=3;
single sharpen keeps 3);
removing any module moves the render >=1.0 from TARGET; the task must be scorable: half strength fails, x0.9 passes.
Instructions for L1 are generated from the program; L2 gets the module set; L3 gets the target only.
Output set: $BENCH_SET under visual_effect_data (bench_pilot = the first pilot, bench_pilot2 = this generator).
Other apps ($BENCH_APP rawtherapee / gimp, see ops.py) use the same generator; their default set is bench_<app>1.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import argparse,base64,csv,io,json,os,random,sys
import httpx,numpy as np
from PIL import Image
from skimage import color
sys.path.insert(0,str(Path(__file__).parent))
import ops

ROOT=Path(__file__).resolve().parents[2]
DATA=gbpaths.DATA
OUT=DATA/os.environ.get('BENCH_SET','bench_pilot' if ops.APP=='darktable' else f'bench_{ops.APP}1')
_meta=OUT/'tasks.jsonl'
if _meta.exists() and (json.loads(_meta.open().readline() or '{}').get('app') or 'darktable')!=ops.APP:
    raise SystemExit(f'{OUT.name} was not made with {ops.APP}: set BENCH_APP / BENCH_SET to match')
# Sets generated before the symbolic-$DEFAULT fix keep its rendering, so their TARGETs and re-renders agree (dt_params).
if OUT.name in ('bench_pilot','bench_pilot2'):
    import dt_params;dt_params.LEGACY_SYMBOLS=True
MIN_DE=6.0
MAX_TOTAL,MAX_TOTAL_LONG=30.0,45.0   # a 5-7 module edit moves further; the pass rule is relative to it anyway
MIN_DE_LOCAL=ops.MIN_DE_LOCAL
# pass = closeness>=0.75 (dE <= 0.25*dE(START,TARGET)) AND dE<=4. v1-v4 used dE<=3 & closeness>=0.7, which failed x0.9 / x1.1
# on large edits; closeness alone passed a v5 result with saturation in the wrong direction (m52: d0 19.6, dE 4.6).
MIN_CLOSE,MAX_DE=0.75,4.0
NEUTRAL=ops.NEUTRAL

def lab(p):return color.rgb2lab(np.asarray(Image.open(p).convert('RGB'),np.float32)/255)
def de(a,b):return float(color.deltaE_ciede2000(a,b).mean())
def passed(dd,d0):return 1-dd/d0>=MIN_CLOSE and dd<=MAX_DE

def scaled(prog,k):
    """Move every numeric field k times as far from neutral (ops.V2_ANCHOR where set) as in the program (k=0.5 half, k=2 double).
    Returns (clipped program, whether clipping changed it)."""
    out={}
    for m,p in prog.items():
        q={}
        for f,v in p.items():
            n=ops.V2_ANCHOR.get(m,{}).get(f,NEUTRAL.get(m,{}).get(f))
            if n is None or f in ops.HUE_PAIRS:q[f]=v;continue
            q[f]=[nn+k*(x-nn) for x,nn in zip(v,n)] if isinstance(v,list) else n+k*(v-n)
        out[m]=q
    c=ops.clean(out)[0];r=ops.quantize(out)   # rounding to the app's stored decimals is not clipping
    return c,any(c[m][f]!=(v if isinstance(v,list) else float(v)) for m,q in r.items() for f,v in q.items())

def sample_single(m,rng):
    fields=ops.OPS[m][2];p={}
    # colour fields only matter with chroma; pair hue with its chroma
    pairs=ops.HUE_PAIRS
    keys=[k for k in fields if k not in pairs];chosen=rng.sample(keys,min(len(keys),rng.choice([1,2])))
    if any(k in fields for k in pairs) and rng.random()<0.6:
        h=rng.choice([k for k in pairs if k in fields]);chosen=[h,pairs[h]]
    for f in chosen:
        lo,hi,_=fields[f]
        if isinstance(lo,tuple):p[f]=[round(rng.uniform(a,b),3) for a,b in zip(lo,hi)];continue
        n=NEUTRAL.get(m,{}).get(f);span=hi-lo
        while True:
            v=rng.uniform(lo,hi)
            if n is None or abs(v-n)>=0.3*span or f in pairs:break
        p[f]=round(v,3)
    return ops.quantize({m:{f:p[f] for f in fields if f in p}})

def b64(p):
    im=Image.open(p).convert('RGB');im.thumbnail((768,768));b=io.BytesIO();im.save(b,'JPEG',quality=90)
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()

# One direction per task keeps LLM-authored programs from collapsing onto the same three modules.
STYLES=['warm golden-hour grade','cool moody look','vintage split-toned film look','punchy high-clarity landscape','soft dreamy portrait',
        'clean bright commercial look','dark low-key dramatic look','faded matte look','crisp hazy-to-clear dehaze','subtle natural correction']

def llm_program(start,rng,mods):
    style=rng.choice(getattr(ops._lib,'STYLES',STYLES));dom=getattr(ops._lib,'DOMAIN','photo')
    prompt=(f'You are a professional {dom} designer using {ops.PRODUCT}. Look at this {dom} and design a tasteful, realistic edit '
            f'in the direction of: {style}. Use EXACTLY these {len(mods)} {ops.UNIT_WORD}s, each once, every one with a visible effect. '
            +(f'They are applied in the order you list them. ' if ops.ORDERED else '')+
            'Choose values inside the ranges.\n'+ops.spec_text(mods)+
            '\nReturn JSON: {"rationale": "...", "steps": [{"module": "<module>", "settings": [{"field": "<field>", "value": value}, ...]}, ...]}')
    body={'model':'Qwen3.5-397B-A17B-FP8','temperature':0.8,'top_p':0.95,'seed':rng.randrange(10**6),'max_tokens':8000,
          'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':b64(start)}}]}],
          'response_format':{'type':'json_schema','json_schema':{'name':'edit','schema':ops.schema(mods,exactly=len(mods))}}}
    r=httpx.post('http://localhost:8001/v1/chat/completions',json=body,timeout=900);r.raise_for_status()
    j=json.loads(r.json()['choices'][0]['message']['content'])
    prog,v0=ops.from_steps(j.get('steps'));prog,viol=ops.clean(prog);viol=v0+viol
    return prog,f"[{style}] "+j.get('rationale',''),viol

def l1_text(prog):
    parts=[]
    for m,p in prog.items():
        fs=', '.join(f'{f} = {p[f]}' for f in ops.OPS[m][2] if f in p);parts.append(f'{ops.OPS[m][0]} ({m}): {fs}')
    return (f'In {ops.PRODUCT}, apply these {ops.UNIT_WORD}s '+('in this order ' if ops.ORDERED else '')+
            'with exactly these settings: '+'; '.join(parts)+'.')

def accept(src,prog,d,tid):
    t=d/'target.png';ops.render(src,prog,t);lt=lab(t);ls=lab(d/'start.png')
    total=de(ls,lt)
    lo=MIN_DE_LOCAL.get(next(iter(prog)),MIN_DE) if len(prog)==1 else MIN_DE
    if not lo<=total<=(MAX_TOTAL_LONG if len(prog)>=5 else MAX_TOTAL):return None,f'total dE {total:.2f}'
    for m in prog:
        if len(prog)==1:break
        rest={k:v for k,v in prog.items() if k!=m};ops.render(src,rest,d/'_tmp.png')
        if de(lab(d/'_tmp.png'),lt)<1.0:return None,f'{m} not visible'
    for k,want in ((0.5,False),(0.9,True)):
        p,clipped=scaled(prog,k)
        ops.render(src,p,d/'_tmp.png');ok=passed(de(lab(d/'_tmp.png'),lt),total)
        if ok!=want:return None,f'x{k} {"passes" if ok else "fails"}'
    (d/'_tmp.png').unlink(missing_ok=True)
    return total,'ok'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--single',type=int,default=20);ap.add_argument('--multi',type=int,default=20);ap.add_argument('--long',type=int,default=0);ap.add_argument('--seed',type=int,default=0)
    args=ap.parse_args();rng=random.Random(args.seed);(OUT/'tasks').mkdir(parents=True,exist_ok=True)
    if hasattr(ops._lib,'sources'):pool=ops._lib.sources()   # apps with their own start assets (Inkscape: Openclipart SVGs)
    else:pool=[(f'PSBench:{t}',None) for t in sorted(r['task_id'] for r in csv.DictReader(open(ROOT/'motivation/benchmark_audit/task_inventory.csv')) if r['benchmark']=='PSBench')]
    sources0=list(pool);rng.shuffle(pool);mods=list(ops.OPS);tasks=[];log=[];used={m:0 for m in mods}
    want=[('single',mods[i%len(mods)]) for i in range(args.single)]+[('multi',2+i%3) for i in range(args.multi)]+[('long',min(5+i%3,len(mods))) for i in range(args.long)]
    for kind,m in want:
        if kind!='single':   # least-used modules first, random tie-break; counted once the task is accepted
            n=m;m=sorted(mods,key=lambda x:(used[x],rng.random()))[:n]
        for attempt in range(15):
            if not pool:pool=list(sources0);rng.shuffle(pool)   # small asset sets (Blender: 160 scenes) are reused with new programs
            src_id,src=pool.pop()
            if src is None:
                ps=src_id.split(':')[1];meta=json.loads((DATA/'sources/PSBench-data'/ps/f'{ps}.json').read_text())
                src=DATA/'sources/PSBench-data'/ps/meta['resources']['input_file']
            tid=f'{kind[0]}{len(tasks):02d}';d=OUT/'tasks'/tid;d.mkdir(parents=True,exist_ok=True)
            try:ops.render(src,{},d/'start.png')
            except Exception as e:log.append((tid,src_id,f'start render {type(e).__name__}'));continue   # e.g. an SVG Inkscape renders too slowly
            if kind=='single':prog,why,viol=sample_single(m,rng),'sampled',[]
            else:
                try:prog,why,viol=llm_program(d/'start.png',rng,m)
                except Exception as e:log.append((tid,src_id,f'llm error {e!r}'[:120]));continue
                if len(prog)!=len(m):log.append((tid,src_id,f'llm gave {len(prog)} of {len(m)} modules'));continue
            try:total,status=accept(src,prog,d,tid)
            except Exception as e:total,status=None,f'render {type(e).__name__}'
            log.append((tid,src_id,status))
            if total is None:print(tid,'rejected',src_id,status,flush=True);continue
            task={'task_id':tid,'app':ops.APP,'kind':kind,'source':src_id,'source_path':str(src),'program':prog,'rationale':why,'violations':viol,
                  'start_target_de00':round(total,2),'modules':sorted(prog),'l1_instruction':l1_text(prog)}
            if kind!='single':
                for x in prog:used[x]+=1
            (d/'program.json').write_text(json.dumps(task,indent=1));tasks.append(task);print(tid,kind,sorted(prog),round(total,2),flush=True);break
    with (OUT/'tasks.jsonl').open('w') as h:
        for t in tasks:h.write(json.dumps(t)+'\n')
    (OUT/'generation_log.json').write_text(json.dumps(log,indent=1))
    print(json.dumps({'tasks':len(tasks),'single':sum(t['kind']=='single' for t in tasks),'multi':sum(t['kind']=='multi' for t in tasks),'long':sum(t['kind']=='long' for t in tasks),'rejected':sum(s!='ok' for *_,s in log)}))
if __name__=='__main__':main()

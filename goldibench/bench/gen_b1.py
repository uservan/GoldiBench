"""B-1 task generator, as agreed in docs/paper-plan.md §3 B-1 (replaces make_pilot.py for the benchmark).

Per task slot (step count k from a fixed quota, generator model alternating):
  1 START = the app's render of a start asset with no edit (photos: PSBench START images; Inkscape: Openclipart; Blender:
    Poly Haven scenes; as before).
  2 The generator LLM sees START, the app's operation library with ranges, the manual's workflow page and the manual
    page of every operation (workflow_text.py). It writes a client-style intent for this image and a draft program of
    exactly k operations (order = application order) with, for every field it sets, a value interval.
    Generators: Qwen3.5-397B and GLM-5.3, alternating per slot; the generator is stored with the task.
  3 Values are sampled uniformly inside the LLM's intervals (clipped to the library range).
  4 The program is rendered and must pass every gate below. If it fails because the overall change is out of range (C3)
    or a step adds too little (C4), the measured numbers go back to the same LLM in plain words and it revises its plan
    (up to --revisions times; values re-drawn from the revised intervals; every revision is stored). Otherwise, or after
    the last revision, the attempt is dropped with its reason and numbers and the slot retries (new asset, same k).
Gates (criteria fixed here, numbers stored per task in program.json["checks"]):
  C3   START->TARGET mean CIEDE2000 in [6, 30] ([6, 45] for k = 5); a single structural tool uses its own lower bound
       (ops.MIN_DE_LOCAL, e.g. sharpen 3), as in make_pilot.py
  CLIP (photo apps and Blender, not Inkscape; added 2026-11-01 after the sample review, user decision) blown area
       (L* > 97) and crushed area (L* < 5) each grow by at most 10 points of the image START -> TARGET; revisable
  C2   the same program rendered twice: dE <= 0.05 (also the C1 oracle replay)
  C3/C4 every step necessary: the program without any one step FAILS the pass rule (pass = closeness >= 0.75 and dE <= 4)
  V-2  x0.9 and x1.1 strength pass (not required for a factor whose values clip); x0.5 and x1.5 fail
  V-3  no-software shortcuts fail: START shifted to TARGET's mean L*a*b*, and Reinhard colour transfer
  C7   identity fails (implied by C3 and the pass rule; stored)
  coverage  an operation is not used in more than --cap-factor x its fair share of steps
  intent    after the gates pass, the same generator sees START, TARGET and the final steps and revises the intent so it
            describes only what the edit does (user decision 2026-11-01: a quarter of the sample intents named looks no
            step produced); the draft intent is kept as intent_draft; the plausibility judges see the revised intent;
            intent and reasons must be complete sentences, the intent without digits or tool names
  plausible TARGET is a result a professional would deliver for the intent: both models judge (plausible.py, validated
            against a visual review of the first samples); any judge rejects -> dropped (user decision 2026-11-01)
  assets    photo apps use only START images that passed asset_screen.py
Stored, not gated (reported): SSIM START->TARGET, the LLM's raw intervals, whether an interval was clipped.
Accepted tasks also get per-step intermediates (renders of the first i steps).
Output: <DATA>/bench_b1_<app>/{tasks/<id>/, tasks.jsonl, generation_log.jsonl}. Resumable: accepted tasks are kept.

  BENCH_APP=gimp python gen_b1.py --n 10 [--workers 6]
"""
import argparse,json,math,os,random,re,threading,time,traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
APP=os.environ.get('BENCH_APP','darktable')
os.environ.setdefault('BENCH_SET',f'bench_b1_{APP}')
import numpy as np,httpx
from PIL import Image
from skimage.metrics import structural_similarity
import make_pilot as mp, ops, workflow_text, plausible
from final_checks import v3

OUT=mp.OUT
GEN={'qwen35':('http://localhost:8001/v1','Qwen3.5-397B-A17B-FP8'),'glm53':('http://localhost:8002/v1','GLM-5.3-Flash')}
GEN_ORDER=['qwen35','glm53']
TOTAL_RANGE={k:(6.0,45.0 if k>=5 else 30.0) for k in range(1,6)}
C2_MAX_DE=0.05
CLIP_MAX_GROWTH=0.10   # fraction of the image
CLIP_GATE=APP!='inkscape'   # vector art legitimately has pure white / black areas
KIND=lambda k:'single' if k==1 else ('long' if k>=5 else 'multi')
lock=threading.RLock()   # re-entrant: log() takes it and is called while it is held (deadlocked 2026-11-01)

def interval_schema(k,allowed=None):
    items=[]
    for m,(_,_,fields) in ops.OPS.items():
        if allowed is not None and m not in allowed:continue
        sets=[]
        for f,(lo,_,_) in fields.items():
            num={'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3} if isinstance(lo,tuple) else {'type':'number'}
            sets.append({'type':'object','additionalProperties':False,'required':['field','lo','hi'],
                         'properties':{'field':{'const':f},'lo':num,'hi':num}})
        items.append({'type':'object','additionalProperties':False,'required':['module','reason','settings'],
                      'properties':{'module':{'const':m},'reason':{'type':'string','maxLength':400},
                                    'settings':{'type':'array','items':{'anyOf':sets},'minItems':1,'maxItems':len(fields)}}})
    return {'type':'object','additionalProperties':False,'required':['intent','steps'],
            'properties':{'intent':{'type':'string','maxLength':600},
                          'steps':{'type':'array','items':{'anyOf':items},'minItems':k,'maxItems':k}}}

def prompt(k,prefer,blocked=()):
    wf,pages,used=workflow_text.manual_block(APP,list(ops.OPS))
    dom=getattr(ops._lib,'DOMAIN','photo')
    order=('They are applied in the order you list them.' if ops.ORDERED else
           f'{ops.PRODUCT} applies them in its own fixed pipeline order.')
    txt=(f'You are a professional working on this {dom} in {ops.PRODUCT}.\n\n'
         f'1. Look at the image and decide what a professional would actually do to it: write the intent as one sentence a '
         f'client could have written (the look they want, no tool names, no numbers; at most 40 words; state the wanted look, do not describe the image).\n'
         f'2. Plan exactly {k} {ops.UNIT_WORD}{"s" if k>1 else ""} from the library below that a professional would use for that intent '
         f'on this image, each once, in a sensible workflow order. {order} Every {ops.UNIT_WORD} must make its own clearly visible '
         f'contribution; do not add one that the others already cover or that undoes another.\n'
         f'The overall change must be clearly visible at a glance when START and the result are side by side (a deliberate '
         f'edit, not a subtle correction), and each {ops.UNIT_WORD}\'s own share of it must be clearly visible too.\n'
         f'3. For every field you set, give an interval [lo, hi] of values that all serve the intent (the task value will be '
         f'drawn from it). Stay inside the library ranges; leave fields you would not touch out.\n'
         +(f'If they suit this image, prefer these less-used {ops.UNIT_WORD}s: {", ".join(prefer)}.\n' if prefer else '')
         +(getattr(ops._lib,'GEN_NOTE','')+'\n' if getattr(ops._lib,'GEN_NOTE','') else '')
         +(f'Not available for this task (already used often enough in the set): {", ".join(blocked)}.\n' if blocked else '')+
         f'\nOperation library (field [min .. max]):\n{ops.spec_text()}\n\n'
         f'Manual, workflow:\n{wf}\n\nManual, per {ops.UNIT_WORD}:\n{pages}\n\n'
         'Return JSON: {"intent": "...", "steps": [{"module": "<module>", "reason": "...", "settings": [{"field": "<field>", "lo": .., "hi": ..}, ...]}, ...]}')
    return txt,used

SENT_END=('.','!','?')
def text_problems(plan):
    """Gate: intent and every reason are complete sentences (guided decoding at a length cap cut them mid-word before
    2026-11-01: 6 of 40 samples) and contain no broken characters."""
    bad=[]
    for n,x in [('intent',plan.get('intent') or '')]+[(f'reason {s.get("module")}',s.get('reason') or '') for s in plan.get('steps',[])]:
        x=x.strip().rstrip('"\')')
        if not x or not x.endswith(SENT_END) or '\ufffd' in x:bad.append(n)
    return bad

def ask(gen,msgs,k,rng,allowed=None):
    base,model=GEN[gen]
    body={'model':model,'temperature':0.8,'top_p':0.95,'seed':rng.randrange(10**6),'max_tokens':12000,'messages':msgs,
          'response_format':{'type':'json_schema','json_schema':{'name':'plan','schema':interval_schema(k,allowed)}}}
    r=httpx.post(f'{base}/chat/completions',json=body,timeout=1200);r.raise_for_status()
    c=r.json()['choices'][0]['message']['content'];return json.loads(c),c

def feedback(why,checks,prog):
    """Plain-language measurement for a revision, or None when the failure is not one a revision addresses."""
    if why.startswith('C3'):
        d0=checks['C3_total']['de'];lo,hi=checks['C3_total']['range']
        return (f'Rendered and measured: the overall change is too {"small" if d0<lo else "large"} '
                f'(mean CIEDE2000 {d0:.1f} between START and the result; it must be between {lo:g} and {hi:g}). '
                + ('Make the edit clearly stronger: widen or move the intervals further from neutral, while it stays a plausible professional result (no garish colour cast, no large crushed or blown areas).' if d0<lo else 'Make the edit milder.'))
    if why.startswith('CLIP'):
        x=checks['CLIP'];parts=[]
        if x['blown'][1]-x['blown'][0]>CLIP_MAX_GROWTH:parts.append(f'pure-white (blown) area grows from {100*x["blown"][0]:.0f}% to {100*x["blown"][1]:.0f}% of the image')
        if x['crushed'][1]-x['crushed'][0]>CLIP_MAX_GROWTH:parts.append(f'pure-black (crushed) area grows from {100*x["crushed"][0]:.0f}% to {100*x["crushed"][1]:.0f}% of the image')
        return ('Rendered and measured: the '+' and the '.join(parts)+f' (at most {100*CLIP_MAX_GROWTH:.0f} points of growth are allowed). '
                'A professional keeps detail in highlights and shadows: revise the plan so the edit keeps its look and stays clearly visible '
                'without blowing out or crushing large areas. Keep the same number of steps.')
    if why.startswith('C4'):
        weak=[m for m,v in checks['C4_necessary'].items() if not v['ok']]
        return (f'Rendered and measured: without {", ".join(weak)} the result still looks almost the same as the full edit, '
                f'so {"that step adds" if len(weak)==1 else "those steps add"} too little. Every step must have a clearly visible '
                f'share of its own: strengthen {"it" if len(weak)==1 else "them"} or replace {"it" if len(weak)==1 else "them"} with another '
                f'{ops.UNIT_WORD}. Keep exactly the same number of steps.')
    if why.startswith('plausible'):
        return ('Looking at the rendered result, it is not a result a professional would deliver for your '
                'intent: '+'; '.join(j['reason'] for j in checks['plausible']['judgments'] if j['acceptable'] is False)+
                ' Revise the plan so the result is a clean, plausible professional edit that matches the intent. Keep the same number of steps.')
    return None

def sample(plan,rng):
    """LLM intervals -> program (values drawn uniformly inside the intervals, clipped to the library range)."""
    prog={};intervals={};clipped=[]
    for s in plan['steps']:
        m=s['module']
        if m in prog:raise ValueError(f'{m} repeated')
        fields=ops.OPS[m][2];p={};iv={}
        for kv in s['settings']:
            f=kv['field'];lo,hi,_=fields[f];a,b=kv['lo'],kv['hi']
            if isinstance(lo,tuple):
                a=[min(max(float(x),l),h) for x,l,h in zip(a,lo,hi)];b=[min(max(float(x),l),h) for x,l,h in zip(b,lo,hi)]
                if [a,b]!=[kv['lo'],kv['hi']]:clipped.append(f'{m}.{f}')
                p[f]=[round(rng.uniform(min(x,y),max(x,y)),3) for x,y in zip(a,b)];iv[f]=[kv['lo'],kv['hi']]
            else:
                x,y=sorted((float(a),float(b)));cx,cy=min(max(x,lo),hi),min(max(y,lo),hi)
                if (cx,cy)!=(x,y):clipped.append(f'{m}.{f}')
                p[f]=round(rng.uniform(cx,cy),3);iv[f]=[x,y]
        prog[m]=p;intervals[m]=iv
    prog,viol=ops.clean(prog)
    return prog,intervals,clipped,viol

def ssim(a,b):
    x=np.asarray(Image.open(a).convert('L'),np.float32);y=np.asarray(Image.open(b).convert('L'),np.float32)
    return float(structural_similarity(x,y,data_range=255))

def gate(src,prog,d):
    """All gates in order; returns (ok, reason, checks). Stops at the first failure (its numbers are kept)."""
    k=len(prog);c={};t=d/'target.png';tmp=d/'_tmp.png'
    ops.render(src,prog,t);ls,lt=mp.lab(d/'start.png'),mp.lab(t);d0=mp.de(ls,lt);lo,hi=TOTAL_RANGE[k]
    if k==1:lo=ops.MIN_DE_LOCAL.get(next(iter(prog)),lo)   # paper-plan C3: dE >= 6, structural single tools (sharpen ...) their own bound
    c['C3_total']={'de':round(d0,3),'range':[lo,hi],'ok':lo<=d0<=hi}
    if not c['C3_total']['ok']:return False,f'C3 total dE {d0:.2f}',c
    L0,L1=ls[...,0],lt[...,0];bl=[float((L0>97).mean()),float((L1>97).mean())];cr=[float((L0<5).mean()),float((L1<5).mean())]
    c['CLIP']={'blown':[round(x,4) for x in bl],'crushed':[round(x,4) for x in cr],'max_growth':CLIP_MAX_GROWTH,'gated':CLIP_GATE,
               'ok':not CLIP_GATE or (bl[1]-bl[0]<=CLIP_MAX_GROWTH and cr[1]-cr[0]<=CLIP_MAX_GROWTH)}
    if not c['CLIP']['ok']:return False,f'CLIP blown {100*bl[0]:.0f}->{100*bl[1]:.0f}% crushed {100*cr[0]:.0f}->{100*cr[1]:.0f}%',c
    ops.render(src,prog,tmp);px=int(np.abs(np.asarray(Image.open(tmp).convert('RGB'),np.int16)-np.asarray(Image.open(t).convert('RGB'),np.int16)).max())
    e=mp.de(mp.lab(tmp),lt);c['C2_repeat']={'de':round(e,4),'max_px':px,'max':C2_MAX_DE,'ok':e<=C2_MAX_DE}
    if not c['C2_repeat']['ok']:return False,f'C2 repeat dE {e:.3f}',c
    c['C7_identity']={'de':round(d0,3),'ok':not mp.passed(d0,d0)}
    r=v3(d/'start.png',t);c['V3']={**r,'ok':not any(x['pass'] for x in r.values())}
    if not c['V3']['ok']:return False,'V-3 shortcut passes: '+','.join(n for n,x in r.items() if x['pass']),c
    if k>1:
        c['C4_necessary']={}
        for m in prog:
            ops.render(src,{x:v for x,v in prog.items() if x!=m},tmp);e=mp.de(mp.lab(tmp),lt)
            c['C4_necessary'][m]={'de':round(e,3),'closeness':round(1-e/d0,3),'ok':not mp.passed(e,d0)}
            if not c['C4_necessary'][m]['ok']:return False,f'C4 {m} unnecessary (dE {e:.2f} without it)',c
    c['V2']={}
    for f,want in ((0.9,True),(1.1,True),(0.5,False),(1.5,False)):
        p,cl=mp.scaled(prog,f)
        if want and cl:c['V2'][str(f)]={'clipped':True,'ok':True};continue
        ops.render(src,p,tmp);e=mp.de(mp.lab(tmp),lt);ok=mp.passed(e,d0)==want
        c['V2'][str(f)]={'de':round(e,3),'clipped':cl,'should_pass':want,'ok':ok}
        if not ok:return False,f'V-2 x{f} {"fails" if want else "passes"} (dE {e:.2f})',c
    if all(c['V2'][x].get('clipped') for x in ('0.9','1.1')):return False,'V-2 both near factors clip',c
    tmp.unlink(missing_ok=True)
    c['ssim_start_target']=round(ssim(d/'start.png',t),4)
    return True,'ok',c

def tool_names_in(text):
    names={m.lower() for m in ops.OPS}|{ops.OPS[m][0].lower() for m in ops.OPS}
    return [n for n in names if len(n)>3 and re.search(r'\b'+re.escape(n.replace('_',' '))+r'\b',text.lower().replace('_',' '))]

MIN_INTENT_WORDS=6
def intent_problems(i):
    bad=text_problems({'intent':i,'steps':[]})
    # '...' passed the sentence check and was stored as an intent (rawtherapee b005, 2026-11-01)
    if len(re.findall(r'[A-Za-z]{2,}',i))<MIN_INTENT_WORDS:bad.append(f'fewer than {MIN_INTENT_WORDS} words')
    if re.search(r'\d',i):bad.append('digits')
    if tool_names_in(i):bad.append(f'tool names {tool_names_in(i)}')
    return bad

def render_steps(src,prog,d):
    names=list(prog)
    for j in range(1,len(names)):ops.render(src,{m:prog[m] for m in names[:j]},d/f'step{j}.png')

def _stats(lab):
    L=lab[...,0];gy,gx=np.gradient(L)
    return {'L':float(L.mean()),'chroma':float(np.hypot(lab[...,1],lab[...,2]).mean()),'warm':float(lab[...,2].mean()),
            'contrast':float(L.std()),'detail':float(np.hypot(gx,gy).mean())}

def border_shift(a,b):
    """Position-dependent brightness change (vignette-like) from lab a -> b: how much more the borders brighten than the
    centre for pixels of the SAME starting brightness. Comparing raw border vs centre means (as before 2026-11-01 round 3)
    read every tone-curve change as a vignette when the borders were darker or brighter than the centre (8 of 43 revised
    intents claimed a darkened/brightened frame that no step made)."""
    La,Lb=a[...,0],b[...,0];h,w=La.shape;c=max(1,min(h,w)//6)
    ring=np.zeros_like(La,bool);ring[:c]=ring[-c:]=True;ring[:,:c]=ring[:,-c:]=True
    cen=np.zeros_like(La,bool);cen[h//3:2*h//3,w//3:2*w//3]=True
    # remove what brightness alone explains: mean change per 2-L* bin over the whole image (a tone curve), then compare
    # the leftover change at the borders with the centre
    dL=Lb-La;bins=np.clip((La//2).astype(int),0,49)
    f=np.bincount(bins.ravel(),dL.ravel(),50)/np.maximum(np.bincount(bins.ravel(),minlength=50),1)
    res=dL-f[bins]
    return float(res[ring].mean()-res[cen].mean())

def is_vignette(m):return 'vignet' in (m+' '+ops.OPS[m][0]).lower()
FRAME_WORDS=re.compile(r'\b(?:borders?|corners?|vignett\w*|framed|framing|(?:darken|brighten|lighten)\w*\s+(?:\w+\s+)?(?:frame|edges?))\b',re.I)

def step_effects(d,prog):
    """Measured visible effect of every step (render before -> after), in words, for the intent revision.
    The generator misread directions (RawTherapee vignette < 0 brightens the borders, 2026-11-01) and the revision kept
    the planned wording; measured facts take the guessing out."""
    names=list(prog);ims=[d/'start.png']+[d/f'step{j}.png' for j in range(1,len(names))]+[d/'target.png']
    labs=[mp.lab(p) for p in ims];st=[_stats(x) for x in labs];out=[]
    for i,m in enumerate(names):
        a,b=st[i],st[i+1];f=[]
        def say(key,pos,neg,unit,th):
            x=b[key]-a[key]
            if abs(x)>=th:f.append(f'{pos if x>0 else neg} by {abs(x):.1f} {unit}')
        say('L','overall brighter','overall darker','L*',1.0)
        v=border_shift(labs[i],labs[i+1]) if is_vignette(m) else 0.0   # lighting / local tools change borders too, but no client calls that a frame
        if abs(v)>=2.0:f.append(f'borders {"brighter" if v>0 else "darker"} than the centre (vignette-like) by {abs(v):.1f} L*')
        r=b['detail']/max(a['detail'],1e-6)
        if r<=0.85:f.append(f'{"strongly blurred" if r<=0.7 else "softer"}: fine detail down {100*(1-r):.0f}%')
        elif r>=1.15:f.append(f'crisper: fine detail up {100*(r-1):.0f}%')
        say('contrast','more tonal contrast','less tonal contrast','(std of L*)',1.0)
        say('chroma','more saturated','less saturated','(mean chroma)',1.0)
        say('warm','warmer / more yellow','cooler / more blue','(mean b*)',1.0)
        out.append(f'- {ops.OPS[m][0]}: '+('; '.join(f) if f else 'no large global change (local / texture effect)'))
    return '\n'.join(out)

def revise_intent(gen,d,draft,prog,rng):
    """The generator rewrites its intent, and the one-sentence reason of every step, so they name only what the final
    edit does (it sees START, TARGET, the steps and each step's measured effect). Returns (intent, {module: reason}).
    Reasons were not revised before round 3 and contradicted the renders or leaked revision feedback ('Replaces sharpen',
    'the blue cast reviewers flagged')."""
    steps='\n'.join(f'- {m} ({ops.OPS[m][0]}): {ops.OPS[m][1]}; set to {json.dumps(v)}' for m,v in prog.items())
    steps+='\n\nMeasured on the renders, what each step actually changed (trust these over the plan):\n'+step_effects(d,prog)
    vig=any(is_vignette(m) for m in prog)
    txt=(f'You planned this edit for the image with the intent:\n"{draft}"\n\nThe edit that was finally applied consists of these '
         f'{ops.UNIT_WORD}s:\n{steps}\n\nImage 1 is START, image 2 is the result.\n'
         f'1. Rewrite the intent as one sentence a client could have written that describes only the look this edit actually '
         f'produces: keep the wording of the original where it still holds, and drop or correct anything the measurements '
         f'contradict (a warming that is not there, a light touch where the change is strong, a darkened frame when the borders '
         f'got brighter). '+('' if vig else 'There is no vignette step, so do not mention borders, corners, edges of the frame or framing. ')+
         f'No tool names, no numbers, at most 40 words, end with a full stop.\n'
         f'2. For every {ops.UNIT_WORD}, write one sentence (at most 30 words) saying what it does to this image, matching the '
         f'measurements. Describe the image only: no mention of earlier attempts, feedback, reviewers or other {ops.UNIT_WORD}s.\n'
         f'Return JSON: {{"intent": "...", "reasons": {{{", ".join(f'"{m}": "..."' for m in prog)}}}}}')
    msgs=[{'role':'user','content':[{'type':'text','text':txt},{'type':'image_url','image_url':{'url':mp.b64(d/'start.png')}},
                                    {'type':'image_url','image_url':{'url':mp.b64(d/'target.png')}}]}]
    schema={'type':'object','additionalProperties':False,'required':['intent','reasons'],'properties':{
        'intent':{'type':'string','maxLength':600},
        'reasons':{'type':'object','additionalProperties':False,'required':list(prog),'properties':{m:{'type':'string','maxLength':400} for m in prog}}}}
    base,model=GEN[gen];last=None;bad=['no answer']
    for _ in range(3):
        body={'model':model,'temperature':0.3,'seed':rng.randrange(10**6),'max_tokens':8000,'messages':msgs,
              'response_format':{'type':'json_schema','json_schema':{'name':'intent','schema':schema}}}
        r=httpx.post(f'{base}/chat/completions',json=body,timeout=1200);r.raise_for_status()
        raw=r.json()['choices'][0]['message']['content']
        if not raw:bad=['no answer (empty content)'];continue
        try:o=json.loads(raw);last=o['intent'].strip();reasons={m:o['reasons'][m].strip() for m in prog}
        except (ValueError,KeyError,TypeError,AttributeError) as e:bad=[f'invalid JSON ({type(e).__name__})'];continue
        bad=revision_problems(last,reasons,vig)
        if not bad:return last,reasons
        # tell the model what was wrong (a retry without it repeated the same tool name, 2026-11-01)
        fix=[]
        for b in bad:
            if b.startswith('tool names'):fix.append(f'the intent uses the tool name(s) {b[len("tool names "):]}; describe the look in other words')
            elif b=='digits':fix.append('the intent contains digits')
            elif b.startswith('fewer than'):fix.append('the intent is not a real sentence; describe the look in one full sentence')
            elif b.startswith('frame'):fix.append(f'the intent mentions {b[len("frame words "):]} but no step darkens or brightens the borders')
            elif b.startswith('reason'):fix.append(f'{b}: give one complete sentence about this image only')
            else:fix.append('the intent is not one complete sentence ending with a full stop')
        msgs=msgs+[{'role':'assistant','content':raw},{'role':'user','content':'Rewrite: '+'; '.join(fix)+'. Return the same JSON.'}]
    raise ValueError(f'intent revision failed: {bad}: {(last or "")[:120]}')

META_WORDS=re.compile(r'\b(replac\w*|previous\w*|earlier|attempt\w*|feedback|reviewers?|flagged|instead of the|distinct(ly)? from)\b',re.I)
def revision_problems(intent,reasons,vignette):
    bad=intent_problems(intent)
    if not vignette:
        w=sorted({x.lower() for x in FRAME_WORDS.findall(intent)})
        if w:bad.append(f'frame words {w}')
    for m,r in reasons.items():
        if not r or r[-1] not in SENT_END or '\ufffd' in r:bad.append(f'reason {m} incomplete')
        elif META_WORDS.search(r):bad.append(f'reason {m} talks about the editing process ("{META_WORDS.search(r).group(0)}")')
    return bad

def plausibility(d,intent,gen):
    """Both models judge whether TARGET is a deliverable professional result for the intent (plausible.py).
    Any judge rejects (or gives no verdict) -> drop. Until round 3 one reject meant manual review; in that round's visual
    review the rejecting judge was right in 12 of 17 split cases, and the user chose to drop them (2026-11-01)."""
    js=[plausible.judge(d/'start.png',d/'target.png',intent,j) for j in (plausible.OTHER[gen],gen)]
    rej=[j for j in js if j['acceptable'] is False];none=[j for j in js if j['acceptable'] is None]
    status='rejected' if rej or none else 'ok'
    return {'judgments':js,'status':status,'ok':status!='rejected'}

def sources():
    """(id, path or None); a PSBench path is resolved only when that asset is used (the shared disk lazily loads files).
    Photo apps use only PSBench START images that passed asset_screen.py (unique, one natural photo, no UI / text / collage)."""
    if APP=='inkscape':   # Openclipart SVGs that passed asset_screen_inkscape.py
        f=mp.DATA/'assets'/'openclipart_screen.jsonl'
        if not f.exists():raise SystemExit('run asset_screen_inkscape.py first')
        ok={r['id'] for r in map(json.loads,open(f)) if r['ok']}
        return [x for x in ops._lib.sources() if x[0].split(':')[1] in ok]
    if hasattr(ops._lib,'sources'):return ops._lib.sources()
    f=mp.DATA/'assets'/'psbench_screen.jsonl'
    if not f.exists():raise SystemExit('run asset_screen.py first (photo start assets are screened before generation)')
    return [(f"PSBench:{r['id']}",None) for r in map(json.loads,open(f)) if r['ok']]

def resolve(src_id,src):
    if src is not None:return src
    ps=src_id.split(':')[1];meta=json.loads((mp.DATA/'sources/PSBench-data'/ps/f'{ps}.json').read_text())
    return mp.DATA/'sources/PSBench-data'/ps/meta['resources']['input_file']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--n',type=int,default=10);ap.add_argument('--workers',type=int,default=6)
    ap.add_argument('--seed',type=int,default=0);ap.add_argument('--attempts',type=int,default=25);ap.add_argument('--cap-factor',type=float,default=1.6);ap.add_argument('--revisions',type=int,default=2)
    a=ap.parse_args();(OUT/'tasks').mkdir(parents=True,exist_ok=True)
    pool=sources();random.Random(a.seed).shuffle(pool);pool_i=[0]
    slots=[(i,1+i%5,GEN_ORDER[(i//5)%2]) for i in range(a.n)]   # k = 1..5 cycling; generator alternates per block of 5
    steps_total=sum(k for _,k,_ in slots);cap=max(2,math.ceil(a.cap_factor*steps_total/len(ops.OPS)))
    done={json.loads(p.read_text())['task_id']:json.loads(p.read_text()) for p in (OUT/'tasks').glob('*/program.json')}
    used={m:0 for m in ops.OPS}
    for t in done.values():
        for m in t['program']:used[m]+=1
    # one task per start asset within a set (the pool order restarts with every run, so skip assets already taken)
    taken={t['source'] for t in done.values()};pool=[x for x in pool if x[0] not in taken]
    logf=open(OUT/'generation_log.jsonl','a')
    def log(r):
        with lock:logf.write(json.dumps(r)+'\n');logf.flush()
    def next_src():
        with lock:
            s=pool[pool_i[0]%len(pool)];pool_i[0]+=1;return s
    def run(slot):
        i,k,gen=slot;tid=f'b{i:03d}'
        if tid in done:return done[tid]
        rng=random.Random(a.seed*100003+i);d=OUT/'tasks'/tid
        for att in range(a.attempts):
            src_id,src=next_src();d.mkdir(parents=True,exist_ok=True);rec={'task_id':tid,'attempt':att,'k':k,'generator':gen,'source':src_id}
            try:
                src=resolve(src_id,src);ops.render(src,{},d/'start.png')
                with lock:
                    prefer=sorted(ops.OPS,key=lambda m:used[m])[:3] if getattr(ops._lib,'PREFER_LEAST_USED',True) else [];blocked=[m for m in ops.OPS if used[m]>=cap]
                allowed=[m for m in ops.OPS if m not in blocked]
                if len(allowed)<k:log({**rec,'status':f'coverage: only {len(allowed)} tools left under cap {cap}'});continue
                txt,pages=prompt(k,prefer,blocked)
                msgs=[{'role':'user','content':[{'type':'text','text':txt},{'type':'image_url','image_url':{'url':mp.b64(d/'start.png')}}]}]
                revisions=[]
                for rev in range(1+a.revisions):
                    plan,raw=ask(gen,msgs,k,rng,allowed)
                    tp=text_problems(plan)
                    if tp:raise ValueError(f'incomplete text: {tp}')
                    prog,intervals,clipped,viol=sample(plan,rng)
                    if len(prog)!=k:raise ValueError(f'{len(prog)} of {k} steps')
                    with lock:over=[m for m in prog if used[m]+1>cap]
                    if over:why,checks=f'coverage cap {cap} reached: {over}',{};break
                    ok,why,checks=gate(src,prog,d)
                    if ok:
                        render_steps(src,prog,d)
                        plan['intent_draft']=plan.get('intent','');plan['reasons_draft']={x['module']:x.get('reason') for x in plan['steps']}
                        plan['intent'],plan['reasons']=revise_intent(gen,d,plan['intent_draft'],prog,rng)
                        checks['plausible']=plausibility(d,plan['intent'],gen)
                        if not checks['plausible']['ok']:
                            ok=False;why='plausible: rejected ('+'; '.join(j['reason'][:80] for j in checks['plausible']['judgments'])+')'
                    revisions.append({'revision':rev,'status':why,'program':prog,'intervals':intervals})
                    fb=None if ok else feedback(why,checks,prog)
                    if ok or fb is None or rev==a.revisions:break
                    msgs+=[{'role':'assistant','content':raw},{'role':'user','content':fb}]
                    log({**rec,'revision':rev,'intermediate':True,'status':why,'checks':checks,'program':prog,'intent':plan.get('intent')})
                if why.startswith('coverage'):log({**rec,'status':why});continue
                ok=why=='ok'
            except Exception as e:
                log({**rec,'status':f'error {type(e).__name__}: {str(e)[:200]}'});continue
            log({**rec,'revision':len(revisions)-1,'status':why,'checks':checks,'program':prog,'intent':plan.get('intent')})
            if not ok:continue
            with lock:
                if any(used[m]+1>cap for m in prog):log({**rec,'status':'coverage cap (race)'});continue
                if src_id in taken:log({**rec,'status':'asset taken (race)'});continue
                for m in prog:used[m]+=1
                taken.add(src_id)
            names=list(prog)
            render_steps(src,prog,d)   # again: the accepted program may come from a later revision than the last render
            task={'task_id':tid,'app':APP,'kind':KIND(k),'steps':k,'generator':gen,'source':src_id,'source_path':str(src),
                  'intent':plan.get('intent'),'intent_draft':plan.get('intent_draft'),'program':prog,'order':names,'intervals':intervals,'interval_clipped':clipped,
                  'reasons':plan['reasons'],'reasons_draft':plan['reasons_draft'],'violations':viol,'manual_pages':pages,
                  'start_target_de00':checks['C3_total']['de'],'modules':sorted(prog),'l1_instruction':mp.l1_text(prog),
                  'checks':checks,'attempts':att+1,'revisions':revisions,'final_feedback_rounds':len(revisions)-1}
            (d/'program.json').write_text(json.dumps(task,indent=1));print(tid,k,gen,names,checks['C3_total']['de'],flush=True);return task
        log({'task_id':tid,'k':k,'generator':gen,'status':'slot failed: attempts exhausted'});return None
    with ThreadPoolExecutor(a.workers) as ex:res=list(ex.map(run,slots))
    tasks=[t for t in res if t]
    (OUT/'tasks.jsonl').write_text(''.join(json.dumps(t)+'\n' for t in sorted(tasks,key=lambda t:t['task_id'])))
    print(json.dumps({'slots':len(slots),'accepted':len(tasks),'cap':cap,'usage':used}))

if __name__=='__main__':main()

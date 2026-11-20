"""Per-task mini manual (B-1 manual experiment, 2026-11-06; run_agent.py --minimanual visual|text, L2 only).

The full manual (run_agent.py --manual) is large and the agent must choose to read it. The mini manual covers only the
tools of the task (the L2 tool set) and is placed in the first message:
  visual  per tool a reference card (text) + one effect sheet of the task's tools on a fixed exemplar (knowledge.sheet:
          per field, tool off + 3 settings; the exemplar is in no B-1 task, never START)
  text    the same cards, no sheet
Cards (v2, 2026-11-06) are written once per (app, tool) by an open model (Qwen3.5-397B-A17B-FP8, served on :8001) from the tool's manual
excerpt (workflow_text.manual_block), its field list (ops.spec_text) and its own effect sheet; the card must not refer to
the sheet, so the text condition reads on its own. v2 also gives the writer the measured change of every sheet setting
(knowledge.stats on the exemplar renders) and ties its magnitude words to them: the v1 cards (kept in cards_v1/, never
used in a run) overstated magnitudes, e.g. GIMP brightness -0.5 "shadows solid black" for a -6.5 L* change. Cards and sheets are cached under visual_effect_data/minimanual/<app>/.
  BENCH_APP=<app> BENCH_SET=bench_b1_<app> python minimanual.py build     # sheets + cards for every library tool
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import base64,io,json,os,sys
from concurrent.futures import ThreadPoolExecutor
import httpx
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).parent))
import ops,knowledge,workflow_text

DATA=gbpaths.DATA
PHOTO=DATA/'sources/PSBench-data/118/118_start.jpg'   # screened ok, used by no B-1 task (checked 2026-11-06)
EXEMPLAR={'darktable':PHOTO,'gimp':PHOTO,'rawtherapee':PHOTO,
          'inkscape':DATA/'assets/openclipart/raw/3458.svg',                                   # unused, screened ok
          'blender':DATA/'assets/polyhaven/scenes/WoodenChair_01__lilienstein__150.blend'}[ops.APP]  # object + HDRI pair unused
OUT=DATA/'minimanual'/ops.APP
WRITER=('http://localhost:8001/v1','Qwen3.5-397B-A17B-FP8')
CARD_WORDS=150

# Fields that show nothing on their own get context (as knowledge.CONTEXT; added here so knowledge.py's runs stay as they were)
CONTEXT={'blender':{('sun','elevation'):{'strength':5.6},('floor','hue'):{'saturation':0.42}},
         'inkscape':{('drop_shadow','offset'):{'opacity':0.7,'blur':1.0},('drop_shadow','blur'):{'opacity':0.7,'offset':1.5},
                     ('drop_shadow','opacity'):{'offset':1.5,'blur':1.0}}}.get(ops.APP,{})
knowledge.CONTEXT.update(CONTEXT)
# Structure tools (sharpen / blur / roughen) are invisible in a 200 px thumbnail: their rows show a 1:1 centre crop of an
# 800 px render instead.
CROP={'darktable':{'sharpen'},'gimp':{'unsharp_mask','gaussian_blur'},'rawtherapee':{'sharpening'},
      'inkscape':{'blur','roughen'}}.get(ops.APP,set())
THUMB=knowledge.THUMB;FONT=knowledge.FONT

def _thumb(p,crop):
    im=Image.open(p).convert('RGB')
    if crop:w,h=im.size;return im.crop((w//2-THUMB//2,h//2-THUMB//2,w//2+THUMB//2,h//2+THUMB//2))
    im.thumbnail((THUMB,THUMB));return im

def sheet(mods):
    """Grid: one row per (tool, field); column 0 = tool off, columns 1-3 = settings (as knowledge.sheet, own exemplar)."""
    mods=list(mods);path=OUT/'sheets'/f'{"+".join(mods)}.png'
    if path.exists():return path
    work=OUT/'renders';work.mkdir(parents=True,exist_ok=True)
    R=[];
    for m in mods:   # per-tool row indices so renders are shared between sheets
        for i,(lab_,progs) in enumerate(knowledge.rows(m)):R.append((m,i,lab_,progs))
    _ensure(mods,work)
    first=_thumb(work/f'off_{"crop" if mods[0] in CROP else "full"}.png',mods[0] in CROP);w,h=first.size;lh=18
    W=4*(THUMB+6)+6;H=len(R)*(h+2*lh+8)+8
    S=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(S);y=6
    for m,i,lab_,progs in R:
        c=m in CROP
        d.text((6,y),f'{ops.OPS[m][0]} ({m}) - varying {lab_}'+(' [centre crop, 1:1]' if c else ''),fill='black',font=FONT)
        ims=[_thumb(work/f'off_{"crop" if c else "full"}.png',c)]+[_thumb(work/f'{m}_{i}_{j}.png',c) for j in range(3)]
        caps=[f'{ops.UNIT_WORD} off']+[knowledge.label(p,lab_) for p in progs]
        for k,(im,cap) in enumerate(zip(ims,caps)):
            x=6+k*(THUMB+6);S.paste(im,(x,y+lh));d.text((x,y+lh+im.size[1]+2),cap[:34],fill='black',font=FONT)
        y+=h+2*lh+8
    path.parent.mkdir(parents=True,exist_ok=True);S.save(path);return path

def _ensure(mods,work):
    jobs=[]
    for m in dict.fromkeys(mods):
        c=m in CROP;jobs.append(({},work/f'off_{"crop" if c else "full"}.png',c))
        for i,(_,progs) in enumerate(knowledge.rows(m)):
            for j,p in enumerate(progs):jobs.append((p,work/f'{m}_{i}_{j}.png',c))
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda j:j[1].exists() or ops.render(EXEMPLAR,j[0],j[1],size=THUMB*4 if j[2] else THUMB*2),jobs))

def _b64(path,side=2000):
    im=Image.open(path).convert('RGB');im.thumbnail((side,side));b=io.BytesIO();im.save(b,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()

PROMPT=('You write a short reference card for the {unit} "{m}" of {product}. The reader must choose its settings to make '
        'an image match a target look, so the card says what each field does to the picture.\n'
        'Inputs: the official manual excerpt, the field list with ranges, and an effect sheet: each row varies one field on '
        'a reference image (first image: {unit} off; next three: the settings written under them; other fields at default).\n'
        'Write plain text, at most {words} words, one line per field: what it visibly changes, which direction does what, '
        'and how strong the change looks at a moderate and at an extreme value (use the field\'s own numbers). Describe only '
        'what is visible. Do not mention the sheet, rows, examples, the reference image or its content, so the card reads '
        'on its own.\nMagnitude words must agree with the MEASURED changes below (same settings as the sheet, measured on the '
        'whole reference image against the {unit} off): a change under 3 is slight, 3-10 clear, over 10 strong; you may '
        'quote rounded numbers. Where a row turns another field on (written "with ..."), describe the field by its effect '
        'relative to the first setting of that row, not by the difference to the tool off. Do not claim effects the numbers do not show (e.g. "pure black" or "blown out" when the '
        'shadow / highlight percentiles barely move).\n\nMANUAL EXCERPT:\n{manual}\n\nFIELDS:\n{spec}\n\nMEASURED:\n{measured}')

STATS=[('L* (lightness)','L'),('chroma','C'),('b* (+yellow/-blue)','b'),('a* (+red/-green)','a'),('contrast (std L*)','Lstd'),
       ('shadows (10th pct L*)','L10'),('highlights (90th pct L*)','L90'),('border minus centre L*','vig'),('detail','det')]

def measured(m):
    work=OUT/'renders';c=m in CROP;off=knowledge.stats(work/f'off_{"crop" if c else "full"}.png');out=[]
    stats=[x for x in STATS if not (ops.APP=='inkscape' and x[1]=='vig')]   # white page around the drawing: no vignette reading
    fmt=lambda a,b:', '.join(f'{n} {a[k]-b[k]:+.1f}' for n,k in stats)
    for i,(lab_,progs) in enumerate(knowledge.rows(m)):
        ctx='(with' in lab_;first=None
        for j,p in enumerate(progs):
            s=knowledge.stats(work/f'{m}_{i}_{j}.png');first=first or s
            out.append(f'- {knowledge.label(p,lab_)}'+(lab_[len(lab_.split(" ")[0]):] if ctx else '')+': vs tool off: '+fmt(s,off)+
                       (f'; vs the first setting of this row (effect of the field alone): {fmt(s,first)}' if ctx and j else ''))
    return ('(detail = mean |Laplacian| of L*, measured on a 1:1 centre crop)\n' if c else '')+'\n'.join(out)

def write_card(m):
    path=OUT/'cards'/f'{m}.json'
    if path.exists():return json.loads(path.read_text())
    _,manual,pages=workflow_text.manual_block(ops.APP,[m]);sp=sheet([m])
    text=PROMPT.format(unit=ops.UNIT_WORD,m=m,product=ops.PRODUCT,words=CARD_WORDS,manual=manual,spec=ops.spec_text([m]),
                       measured=measured(m))
    body={'model':WRITER[1],'temperature':0,'max_tokens':12000,
          'messages':[{'role':'user','content':[{'type':'text','text':text},{'type':'image_url','image_url':{'url':_b64(sp)}}]}]}
    r=httpx.post(f'{WRITER[0]}/chat/completions',json=body,timeout=900);r.raise_for_status()
    card=r.json()['choices'][0]['message']['content'].strip()
    rec={'tool':m,'version':2,'card':card,'words':len(card.split()),'writer':WRITER[1],'sheet':str(sp),'manual_pages':pages,'prompt':text}
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(rec,indent=1));return rec

CARDS_NOTE=('TOOL NOTES for the {unit}s of this task (reference cards written from the manual and from example renders on '
            'another image, not START):\n')
SHEET_NOTE=('EFFECT EXAMPLES for the same {unit}s: each row varies one field of one {unit} on a reference image (not START); '
            'the first image of a row has that {unit} off, the next three use the settings written under them (other '
            'fields at default).')

def blocks(task,visual,img):
    """Message parts for the first message (after TARGET). img(path, side) -> image part, as in run_agent."""
    mods=task['modules'];cards='\n\n'.join(f'[{m}]\n'+write_card(m)['card'] for m in mods)
    parts=[{'type':'text','text':CARDS_NOTE.format(unit=ops.UNIT_WORD)+cards}]
    if visual:parts+=[{'type':'text','text':SHEET_NOTE.format(unit=ops.UNIT_WORD)},img(sheet(mods),2400)]
    return parts

if __name__=='__main__':
    if sys.argv[1:]==['build']:
        for m in ops.OPS:
            c=write_card(m);print(m,c['words'],'words',flush=True)
    elif sys.argv[1:2]==['sheets']:   # task sheets for a subset file (one task id per line)
        tasks={json.loads(l)['task_id']:json.loads(l) for l in gbpaths.open_tasks(DATA/os.environ['BENCH_SET']/'tasks.jsonl')}
        for t in open(sys.argv[2]).read().split():print(t,sheet(tasks[t]['modules']),flush=True)

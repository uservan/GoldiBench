"""Knowledge given to the agent in the injection experiment (L2, run_agent.py --knowledge), one block per allowed tool.

  text         the module's page of the pinned darktable 5.6 manual (first TEXT_CHARS characters; darktable only)
  image        effect sheet on a fixed photo outside every task set (PSBench 003): per field, tool off + 3 settings
  image_state  the same sheet rendered on the task's own START (state-conditioned examples; never the TARGET program)
  table_state  the image_state renders as numbers: per field setting, measured change of image statistics vs tool off
  table_state_diff  table_state + the same statistics measured for TARGET - START (perception oracle: the agent no
               longer has to see the difference, only to invert the table)
  diff_image   (2026-11-15) the difference shown, not measured: per-pixel TARGET - START in CIELAB as three maps (L*, a*,
               b*) on a diverging scale with a colour bar each; no tool information
Sheets vary one field at a time, other fields at neutral; a hue field is shown with its chroma/saturation field at 70 %.
Works for every $BENCH_APP; sheets are cached under <set>/knowledge/. (bench_pilot/knowledge holds the first sheets, on
PSBench 436, which bench_gimp1 uses as a task source.)
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,re,sys
import numpy as np
from scipy import ndimage
from skimage import color
from bs4 import BeautifulSoup
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).parent))
import ops
from make_pilot import NEUTRAL,OUT as SET

DATA=gbpaths.DATA
OUT=SET/'knowledge'
MANUAL=DATA/'manuals/darktable/docs.darktable.org/usermanual/5.6/en/module-reference/processing-modules'
PAGE={'exposure':'exposure','colisa':'contrast-brightness-saturation','levels':'levels','shadhi':'shadows-and-highlights',
      'colorbalancergb':'color-balance-rgb','splittoning':'split-toning','bilat':'local-contrast','sharpen':'sharpen',
      'vignette':'vignetting','hazeremoval':'haze-removal'}
EXEMPLAR=DATA/'sources/PSBench-data/003/003_start.jpg'   # in no task set and never tried by the generators
TEXT_CHARS=4000
HUE_PAIR=ops.HUE_PAIRS
THUMB=200
# Fields that show nothing on their own get this context (split-toning balance needs both tints on; a radius or shape
# needs its tool's strength, which FIXED pins to neutral).
CONTEXT={'darktable':{('splittoning','balance'):{'shadow_hue':0.6,'shadow_saturation':0.7,'highlight_hue':0.1,'highlight_saturation':0.7}},
         'gimp':{('unsharp_mask','radius'):{'amount':1.5},('softglow','glow_radius'):{'brightness':0.35}},
         'rawtherapee':{('sharpening','radius'):{'amount':400.0},('local_contrast','radius'):{'amount':0.5},
                        ('vignette','feather'):{'strength':-1.5},('vignette','roundness'):{'strength':-1.5}}}.get(ops.APP,{})

def manual_text(m):
    soup=BeautifulSoup((MANUAL/PAGE[m]/'index.html').read_text(errors='ignore'),'html.parser')
    for t in soup(['script','style','nav','header','footer','aside']):t.decompose()
    node=soup.select_one('main') or soup.select_one('article') or soup.body
    text=re.sub(r'\n{2,}','\n',node.get_text('\n',strip=True))
    return text[:TEXT_CHARS]

def text_block(modules):
    return '\n\n'.join(f'=== darktable manual: {ops.OPS[m][0]} ({m}) ===\n{manual_text(m)}' for m in modules)

def spread(lo,hi,n):
    """Three settings that all differ from neutral n: both ends and the half-way point on the wider side of n."""
    if n is None or not lo<=n<=hi:return [lo,(lo+hi)/2,hi]
    if n<=lo:return [lo+(hi-lo)*k for k in (1/3,2/3,1)]
    if n>=hi:return [hi-(hi-lo)*k for k in (1/3,2/3,1)]
    return [lo,n+(hi-n)/2,hi] if hi-n>=n-lo else [lo,n-(n-lo)/2,hi]

def rows(m):
    """(label, [3 programs]) per field, one field varied, the others left at default."""
    out=[];fields=ops.OPS[m][2];chroma_of={v:k for k,v in HUE_PAIR.items() if k in fields}
    for f,(lo,hi,_) in fields.items():
        if isinstance(lo,tuple):
            n=NEUTRAL[m][f]
            for i,name in enumerate(('black','grey','white')):
                out.append((f'{f}[{name}]',[{m:{f:[round(v,3) if j==i else n[j] for j in range(3)]}} for v in spread(lo[i],hi[i],n[i])]))
        elif f in HUE_PAIR:          # hue: shown at 70 % of its chroma/saturation range
            c=HUE_PAIR[f];cv=round(fields[c][1]*0.7,3)
            out.append((f'{f} (with {c}={cv:g})',[{m:{f:round(lo+(hi-lo)*k,3),c:cv}} for k in (0,1/3,2/3)]))
        elif f in chroma_of:         # chroma: shown at a fixed hue
            h=chroma_of[f];hv=round(fields[h][1]*0.6,3)
            out.append((f'{f} (with {h}={hv:g})',[{m:{h:hv,f:round(v,3)}} for v in spread(lo,hi,0.0)]))
        else:
            ctx=CONTEXT.get((m,f),{});tag=f' (with {", ".join(f"{k}={v}" for k,v in ctx.items())})' if ctx else ''
            out.append((f+tag,[{m:{**ctx,f:round(v,3)}} for v in spread(lo,hi,NEUTRAL.get(m,{}).get(f))]))
    return out

def label(p,f):
    """Caption: the varied field's value only (context fields are named in the row title)."""
    m,v=next(iter(p.items()));name=f.split(' ')[0].split('[')[0]
    return f'{name}={v[name]}'

FONT=ImageFont.load_default(size=13)

def sheet(src,modules,path):
    """Grid image: one row per (module, field); column 0 = module off (START), columns 1-3 = settings."""
    path=Path(path)
    if path.exists():return path
    work=path.parent/(path.stem+'_parts');work.mkdir(parents=True,exist_ok=True)
    jobs=[('off',{},work/'off.png')]
    R=[(m,lab_,progs) for m in modules for lab_,progs in rows(m)]
    for i,(m,_,progs) in enumerate(R):
        for j,p in enumerate(progs):jobs.append((f'{i}_{j}',p,work/f'{i}_{j}.png'))
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda j:j[2].exists() or ops.render(src,j[1],j[2],size=THUMB*2),jobs))
    def thumb(p):
        im=Image.open(p).convert('RGB');im.thumbnail((THUMB,THUMB));return im
    off=thumb(work/'off.png');w,h=off.size;lh=18
    W=4*(w+6)+6;H=len(R)*(h+2*lh+8)+8
    S=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(S);y=6
    for i,(m,lab_,progs) in enumerate(R):
        d.text((6,y),f'{ops.OPS[m][0]} ({m}) - varying {lab_}',fill='black',font=FONT)
        ims=[off]+[thumb(work/f'{i}_{j}.png') for j in range(3)]
        caps=[f'{ops.UNIT_WORD} off']+[label(p,lab_) for p in progs]
        for k,(im,cap) in enumerate(zip(ims,caps)):
            x=6+k*(w+6);S.paste(im,(x,y+lh));d.text((x,y+lh+h+2),cap[:34],fill='black',font=FONT)
        y+=h+2*lh+8
    S.save(path);return path

def sheet_for(task,kind):
    mods=task['modules']
    if kind=='image':return sheet(EXEMPLAR,mods,OUT/'exemplar'/f'{"+".join(mods)}.png')
    return sheet(task['source_path'],mods,OUT/'state'/f'{task["task_id"]}.png')

SHEET_NOTE=('EFFECT EXAMPLES: each row varies one field of one {unit} on {what}; the first image of a row is the photo with '
            'that {unit} off, the next three use the settings written under them (other fields at default).')
WHAT={'image':'a reference photo (not START)','image_state':'START itself'}

def note(kind):return SHEET_NOTE.format(unit=ops.UNIT_WORD,what=WHAT[kind])

STATS=[('L*','L'),('a*','a'),('b*','b'),('C*','C'),('contrast','Lstd'),('shadows','L10'),('highlights','L90'),
       ('border-center','vig'),('detail','det')]
TABLE_NOTE=('EFFECT TABLE, measured on START: each line is START with one field of one {unit} changed (other fields default) '
            'minus START with that {unit} off. CIELAB statistics: L* lightness 0-100, a* green(-)/red(+), b* blue(-)/yellow(+), '
            'C* chroma, contrast = std of L*, shadows / highlights = 10th / 90th percentile of L*, border-center = mean L* '
            'of the outer 15 % minus the central half, detail = mean |Laplacian| of L* (sharpness).')

def stats(path,size=THUMB*2):
    im=Image.open(path).convert('RGB');im.thumbnail((size,size),Image.LANCZOS)
    l=color.rgb2lab(np.asarray(im,np.float32)/255);L=l[...,0];h,w=L.shape;bh,bw=int(h*.15),int(w*.15)
    border=np.ones_like(L,bool);border[bh:h-bh,bw:w-bw]=False
    return {'L':L.mean(),'a':l[...,1].mean(),'b':l[...,2].mean(),'C':np.hypot(l[...,1],l[...,2]).mean(),'Lstd':L.std(),
            'L10':np.percentile(L,10),'L90':np.percentile(L,90),'vig':L[border].mean()-L[h//4:3*h//4,w//4:3*w//4].mean(),
            'det':np.abs(ndimage.laplace(L)).mean()}

def fmt(d):return ', '.join(f'{n} {d[k]:+.1f}' for n,k in STATS)

def table_for(task,with_diff=False):
    """Text Effect Oracle from the image_state renders (same settings as the sheet), optionally with TARGET - START."""
    sheet_for(task,'image_state');work=OUT/'state'/f'{task["task_id"]}_parts';off=stats(work/'off.png')
    R=[(m,lab_,progs) for m in task['modules'] for lab_,progs in rows(m)];lines=[]
    for i,(m,lab_,progs) in enumerate(R):
        for j,p in enumerate(progs):
            s=stats(work/f'{i}_{j}.png');lines.append(f'- {m}: {label(p,lab_)}'+(lab_[len(lab_.split(" ")[0]):] if '(with' in lab_ else '')
                                                       +': '+fmt({k:s[k]-off[k] for k in s}))
    text=TABLE_NOTE.format(unit=ops.UNIT_WORD)+'\n'+'\n'.join(lines)
    if with_diff:
        d=SET/'tasks'/task['task_id'];a,b=stats(d/'start.png'),stats(d/'target.png')
        text+='\nMEASURED DIFFERENCE, TARGET minus START (same statistics): '+fmt({k:b[k]-a[k] for k in a})
    return text

DIFF_NOTE=('DIFFERENCE MAPS: per pixel, TARGET minus START in CIELAB. Left: L* (lightness; red = TARGET lighter, blue = '
           'darker). Middle: a* (red = TARGET redder, blue = greener). Right: b* (red = TARGET yellower, blue = bluer). '
           'White = no change; the bar under each map gives the scale in CIELAB units.')
def _lab(path,size):
    im=Image.open(path).convert('RGB');im.thumbnail((size,size),Image.LANCZOS);return color.rgb2lab(np.asarray(im,np.float32)/255)
def diff_image_for(task,size=360):
    """Three diverging maps of TARGET - START (L*, a*, b*), red positive / blue negative, scale = 99th pct of |diff|."""
    path=OUT/'diff'/f'{task["task_id"]}.png'
    if path.exists():return path
    path.parent.mkdir(parents=True,exist_ok=True);d=SET/'tasks'/task['task_id']
    a,b=_lab(d/'start.png',size),_lab(d/'target.png',size)
    if a.shape!=b.shape:b=np.asarray(Image.fromarray(np.uint8(np.clip(color.lab2rgb(b)*255,0,255))).resize(a.shape[1::-1]),np.float32);b=color.rgb2lab(b/255)
    h,w=a.shape[:2];bar=14;lh=16;W=3*w+4*8;H=lh+h+bar+lh+8
    S=Image.new('RGB',(W,H),'white');dr=ImageDraw.Draw(S)
    for k,(name,ch) in enumerate((('L*',0),('a*',1),('b*',2))):
        dlt=b[...,ch]-a[...,ch];sc=max(1.0,float(np.percentile(np.abs(dlt),99)));v=np.clip(dlt/sc,-1,1)
        r=np.where(v>0,1,1+v);g=1-np.abs(v);bl=np.where(v<0,1,1-v)   # white -> red (+) / blue (-)
        x=8+k*(w+8);S.paste(Image.fromarray(np.uint8(np.stack([r,g,bl],-1)*255)),(x,lh))
        dr.text((x,0),f'delta {name} (TARGET - START)',fill='black',font=FONT)
        ramp=np.linspace(-1,1,w)[None,:].repeat(bar,0);rr=np.where(ramp>0,1,1+ramp);gg=1-np.abs(ramp);bb=np.where(ramp<0,1,1-ramp)
        S.paste(Image.fromarray(np.uint8(np.stack([rr,gg,bb],-1)*255)),(x,lh+h+2))
        y=lh+h+bar+4;dr.text((x,y),f'-{sc:.1f}',fill='black',font=FONT);dr.text((x+w//2-4,y),'0',fill='black',font=FONT)
        dr.text((x+w-34,y),f'+{sc:.1f}',fill='black',font=FONT)
    S.save(path);return path

if __name__=='__main__':
    tasks=[json.loads(l) for l in gbpaths.open_tasks(SET/'tasks.jsonl')]
    for t in tasks:
        for k in ('image','image_state'):print(t['task_id'],k,sheet_for(t,k),flush=True)

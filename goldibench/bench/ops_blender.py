"""Operation library on Blender 4.5.15 LTS (BENCH_APP=blender). Start scenes are built from CC0 Poly Haven assets
(fetch_polyhaven.py): each of the 80 models on a ground plane under two HDRIs (blender_bench.py build). A program sets
the properties a Blender user edits for the look of a render: Color Management (exposure, gamma, white balance), the
World (HDRI strength and rotation), an added Sun light, the model's materials (a Hue/Saturation/Value node on Base
Color, Principled roughness), camera depth of field and a compositor Glare node. The edit state is the saved .blend.
Renders: Cycles on CPU, 64 samples + OIDN denoise, seed 0 (deterministic), AgX view transform, long side = size.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import json,os,random,subprocess,tempfile
from concurrent.futures import ThreadPoolExecutor

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
BLENDER=LOCAL/'apps/blender-4.5.15/blender'
SCRIPT=Path(__file__).with_name('blender_bench.py')
DATA=gbpaths.DATA
ASSETS=DATA/'assets/polyhaven'

PRODUCT='Blender'
ORDERED=False
UNIT_WORD='setting group'
DOMAIN='3D render'
OPS={
 'exposure':('Color Management > Exposure','exposure of the render',{'ev':(-2.0,2.0,'stops')}),
 'gamma':('Color Management > Gamma','display gamma (>1 brighter midtones)',{'gamma':(0.5,2.0,'')}),
 'white_balance':('Color Management > White Balance','temperature: LOWER values make the render cooler / bluer, higher values warmer / yellower (6500 = unchanged); tint above 10 more magenta, below 10 greener (10 = unchanged)',{'temperature':(3000.0,10000.0,'K'),'tint':(-40.0,40.0,'')}),
 'world':('World > Background (HDRI)','strength of the environment light and its rotation about the vertical axis',
          {'strength':(0.2,3.0,''),'rotation':(-180.0,180.0,'degrees')}),
 'sun':('Add > Light > Sun','a sun light added to the scene',{'strength':(0.0,8.0,'W/m2'),'elevation':(5.0,60.0,'degrees'),'azimuth':(0.0,360.0,'degrees')}),
 'floor':('Ground plane > Material (Principled BSDF Base Color / Roughness)','the ground the object stands on (a large part of the frame): value sets how light it is (0.35 = unchanged mid grey, 0.05 near black, 0.9 near white); saturation > 0 tints it with the hue (0 red, 0.08 orange/brown, 0.15 yellow, 0.33 green, 0.6 blue); roughness low = glossy reflective floor, 0.8 = unchanged matte',
           {'hue':(0.0,1.0,''),'saturation':(0.0,0.6,''),'value':(0.03,0.9,''),'roughness':(0.05,1.0,'')}),
 'haze':('Add > UV Sphere + Principled Volume (fog volume around camera and scene)','atmospheric haze filling the scene: higher density = thicker fog that washes out contrast and the background (0.01 light haze, 0.03 clear fog, 0.08 heavy fog)',
          {'density':(0.0,0.08,'')}),
}
STYLES=['warm golden-hour light','cold blue night look','high-key bright product shot','low-key dramatic look','soft overcast look',
        'vivid stylised colours','muted desaturated look','dreamy glow','harsh midday sun','cinematic teal-and-orange look']
# Shown to the task generator (gen_b1.py): exposure / gamma / white balance alone are a global colour change of the render,
# which a no-software colour transfer reproduces (V-3 rejected 7 / 9 first attempts, 2026-11-01).
GEN_NOTE=('This is a 3D scene: the edit must change the scene itself (lights, the object\'s material, the camera), '
          'not only the overall colour or exposure of the render; use at least one of world, sun, floor, haze.')
# Library redesign 2026-11-01 (user asked): material / gloss / dof / glare removed: a strong setting changed the whole render
# by mean dE00 1.3 / 0.6 / 0.9 / 0.2 (4 scenes), so they could never be a necessary step (C4) and Blender produced 0 tasks
# in 60 attempts. Added floor (ground material, dE 4-11) and haze (fog box, dE 2-14 at density 0.03-0.2), both measured on
# the same scenes and checked by eye. 2026-11-02 01:25 review: the 12x12x6 fog box showed its faces as hard lines on the floor
# and in glossy reflections (b003 b008 b009 b017) -> fog sphere r=30 around the camera; density re-measured on 4 scenes:
# 0.01 -> dE 2.8-3.7, 0.02 -> 4.7-7.4, 0.04 -> 7.8-17, 0.08 -> 13-37; range now 0-0.08. Tighter framing was tried and dropped (material 1.3 -> 2.0 only).
# The generic "prefer less-used tools" hint pushed the generator to material / gloss / dof / glare, which are less used
# precisely because they keep failing C4 (too weak to be necessary): 0 accepted in ~40 final attempts, 2026-11-01 17:25.
# Coverage is still bounded by the per-tool cap.
PREFER_LEAST_USED=False
FIXED={}
NEUTRAL={'exposure':{'ev':0},'gamma':{'gamma':1},'white_balance':{'temperature':6500,'tint':10},'world':{'strength':1,'rotation':0},
         'sun':{'strength':0},'floor':{'hue':0,'saturation':0,'value':0.35,'roughness':0.8},'haze':{'density':0}}
HUE_PAIRS={'azimuth':'strength'}
DECIMALS={'white_balance':{'temperature':0,'tint':1},'world':{'rotation':0},'sun':{'elevation':0,'azimuth':0},'haze':{'density':3}}
MIN_DE_LOCAL={}

def _build(model,hdri,rot,out):
    c={'model':str(ASSETS/'models'/model/f'{model}.gltf'),'hdri':str(ASSETS/'hdris'/hdri/f'{hdri}.hdr'),'rotation':rot,'out':str(out)}
    subprocess.run([str(BLENDER),'-b','--factory-startup','-P',str(SCRIPT),'--','build',json.dumps(c)],capture_output=True,timeout=600)
    if not out.exists():raise RuntimeError(f'build failed: {out.name}')

def sources():
    """Start scenes (id, .blend): every model under two HDRIs and HDRI rotations drawn with seed 0; built once."""
    import csv
    rows=list(csv.DictReader(open(ASSETS/'manifest.csv')));ms=[r['id'] for r in rows if r['kind']=='model'];hs=[r['id'] for r in rows if r['kind']=='hdri']
    rng=random.Random(0);spec=[(m,h,rng.randrange(0,360,15)) for m in ms for h in rng.sample(hs,2)]
    d=ASSETS/'scenes';d.mkdir(exist_ok=True)
    out=[(f'polyhaven:{m}+{h}@{r}',d/f'{m}__{h}__{r}.blend') for m,h,r in spec]
    todo=[(m,h,r,p) for (m,h,r),(_,p) in zip(spec,out) if not p.exists()]
    with ThreadPoolExecutor(16) as pool:list(pool.map(lambda x:_build(*x),todo))
    return out

def render_steps(src,steps,out,size,save=None):
    c={'blend':str(src),'steps':[[m,v] for m,v in steps],'out':str(Path(out).with_suffix('')),'size':size or 1024,'save':str(save) if save else None}
    with tempfile.TemporaryDirectory(dir=os.environ.get('VE_TMP')) as t:
        r=subprocess.run([str(BLENDER),'-b','--factory-startup','-t',os.environ.get('BLENDER_THREADS','8'),'-P',str(SCRIPT),'--','render',json.dumps(c)],   # -t: 6 unbounded renders took ~60 cores and starved the other apps (2026-11-01)
                         capture_output=True,text=True,timeout=900,cwd=t)
    if not Path(out).exists():raise RuntimeError('blender render failed: '+(r.stdout+r.stderr)[-800:])
    return Path(out)

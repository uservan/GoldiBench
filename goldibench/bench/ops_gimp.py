"""Operation library on GIMP 3.2.6 (BENCH_APP=gimp). Each tool is one Colors / Filters menu entry, i.e. one GEGL
operation applied to the (flattened) photo; a program applies its filters in the order given (ORDERED), each once.
Program fields are the operation's config properties (GEGL / GimpOperationConfig units); fields not listed keep the
filter default unless FIXED pins them. Rendering runs gimp-console with gimp_batch.py; one GIMP start renders a list.
Ranges were chosen by rendering each field at its ends on PSBench photos (visible, not destructive).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import fcntl,json,os,shutil,subprocess,tempfile

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
APPRUN=LOCAL/'apps/gimp-3.2.6/squashfs-root/AppRun-console'
BATCH=Path(__file__).with_name('gimp_batch.py')
# A fresh HOME makes GIMP query every plug-in first (~20 s per start); each run gets a copy of one initialised config.
HOME_TEMPLATE=LOCAL/'gimp_home'

PRODUCT='GIMP'
ORDERED=True
UNIT_WORD='filter'
# filter -> (name shown to models, what it does, {field: (min, max, unit/help)})
OPS={
 'brightness_contrast':('Colors > Brightness-Contrast','global brightness and contrast',{'brightness':(-0.5,0.5,''),'contrast':(-0.5,0.5,'')}),
 'exposure':('Colors > Exposure','exposure in stops (> 0 brighter); black_level > 0 darkens the shadows, < 0 lifts them',{'exposure':(-1.5,1.5,'EV'),'black_level':(-0.05,0.05,'')}),
 'color_temperature':('Colors > Color Temperature','changes the white balance: intended temperature, original fixed at 6500 K '
                      '(below 6500 cools, above warms)',{'intended_temperature':(4000.0,9500.0,'K')}),
 'hue_saturation':('Colors > Hue-Saturation','hue rotates every colour by hue x 180 degrees; saturation and lightness > 0 increase, < 0 decrease',
                   {'hue':(-0.25,0.25,'-1..1 = -180..180 deg'),'saturation':(-0.8,0.8,''),'lightness':(-0.3,0.3,'')}),
 'color_balance':('Colors > Color Balance','shifts the midtones towards red/green/blue (negative: cyan/magenta/yellow)',
                  {'cyan_red':(-0.6,0.6,''),'magenta_green':(-0.6,0.6,''),'yellow_blue':(-0.6,0.6,'')}),
 'levels':('Colors > Levels','input black point (raising it darkens shadows), white point (lowering it brightens highlights) and gamma (> 1 brighter midtones, < 1 darker)',
           {'low_input':(0.0,0.3,'0..1'),'high_input':(0.7,1.0,'0..1'),'gamma':(0.4,2.5,'')}),
 'shadows_highlights':('Colors > Shadows-Highlights','shadows > 0 lifts dark regions, highlights < 0 darkens bright regions (local; little effect on images without such regions)',{'shadows':(0.0,100.0,''),'highlights':(-80.0,0.0,'')}),
 'unsharp_mask':('Filters > Enhance > Sharpen (Unsharp Mask)','unsharp-mask sharpening',{'radius':(0.5,5.0,'px'),'amount':(0.0,3.0,'')}),
 'gaussian_blur':('Filters > Blur > Gaussian Blur','blurs the image',{'size':(1.0,10.0,'px std-dev')}),
 'vignette':('Filters > Light and Shadow > Vignette','darkens the borders: smaller radius reaches further in, larger softness gives a wider, darker fall-off',{'radius':(1.3,2.5,''),'softness':(0.2,1.0,'')}),
 'softglow':('Filters > Artistic > Softglow','glow of the bright areas',{'glow_radius':(2.0,30.0,'px'),'brightness':(0.1,0.6,'')}),
}
# field -> (operation, [gegl properties set to scale*value]); FIXED values are written the same way
OP={'brightness_contrast':'gimp:brightness-contrast','exposure':'gegl:exposure','color_temperature':'gegl:color-temperature',
    'hue_saturation':'gimp:hue-saturation','color_balance':'gimp:color-balance','levels':'gimp:levels',
    'shadows_highlights':'gegl:shadows-highlights','unsharp_mask':'gegl:unsharp-mask','gaussian_blur':'gegl:gaussian-blur',
    'vignette':'gegl:vignette','softglow':'gegl:softglow'}
PROPS={'black_level':['black-level'],'intended_temperature':['intended-temperature'],'cyan_red':['cyan-red'],
       'magenta_green':['magenta-green'],'yellow_blue':['yellow-blue'],'low_input':['low-input'],'high_input':['high-input'],
       'radius':{'unsharp_mask':['std-dev'],'vignette':['radius']},'amount':['scale'],'size':['std-dev-x','std-dev-y'],
       'glow_radius':['glow-radius']}
# Settings every instance writes, as the menu entry would (enums / modes the fields belong to).
SETTINGS={'hue_saturation':{'range':{'enum':'Gimp.HueRange','name':'ALL'}},
          'color_balance':{'range':{'enum':'Gimp.TransferMode','name':'MIDTONES'},'preserve-luminosity':True},
          'levels':{'channel':{'enum':'Gimp.HistogramChannel','name':'VALUE'},'trc':{'enum':'Gimp.TRCType','name':'PERCEPTUAL'},'linear':False},
          'color_temperature':{'original-temperature':6500.0}}
# "omitted field = no effect": defaults with an effect (unsharp-mask amount 0.5, softglow brightness 0.3) are pinned
FIXED={'unsharp_mask':{'amount':0.0},'softglow':{'brightness':0.0}}
NEUTRAL={'brightness_contrast':{'brightness':0,'contrast':0},'exposure':{'exposure':0,'black_level':0},'color_temperature':{'intended_temperature':6500},
         'hue_saturation':{'hue':0,'saturation':0,'lightness':0},'color_balance':{'cyan_red':0,'magenta_green':0,'yellow_blue':0},
         'levels':{'low_input':0,'high_input':1,'gamma':1},'shadows_highlights':{'shadows':0,'highlights':0},'unsharp_mask':{'amount':0},
         'gaussian_blur':{'size':0},'vignette':{'radius':10.0},'softglow':{'brightness':0}}
# V-2 strength scaling reference where it differs from NEUTRAL (2026-11-02, user decision): radius 10 is the true no-op
# (radius 5 rendered dE00 0.2), but it lies far outside the allowed 1.3-2.5, so scaling x0.9 around it moved radius ~0.85
# (over half the range) and 15/16 vignette tasks failed V-2; scaling keeps the old reference 5.
V2_ANCHOR={'vignette':{'radius':5.0}}
HUE_PAIRS={}
DECIMALS={}
MIN_DE_LOCAL={'unsharp_mask':3.0,'gaussian_blur':3.0}

def props(tool,values):
    out=dict(SETTINGS.get(tool,{}))
    for f,v in values.items():
        names=PROPS.get(f,[f])
        if isinstance(names,dict):names=names[tool]
        for n in names:out[n]=float(v)
    return out

def _template():
    with open(str(HOME_TEMPLATE)+'.lock','w') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX)
        if not (HOME_TEMPLATE/'.ready').exists():
            shutil.rmtree(HOME_TEMPLATE,ignore_errors=True);HOME_TEMPLATE.mkdir(parents=True)
            subprocess.run([str(APPRUN),'-i','-n','--no-fonts','-d','--quit','--batch-interpreter','python-fu-eval','-b','pass'],
                           capture_output=True,timeout=600,cwd=HOME_TEMPLATE,env={**os.environ,'HOME':str(HOME_TEMPLATE)})
            (HOME_TEMPLATE/'.ready').touch()
    return HOME_TEMPLATE

def run_batch(jobs,timeout=1800):
    """jobs [{'src','out','size','steps': [(tool, {field: value})]}] -> {out: error} for failed ones (empty = all ok)."""
    tpl=_template()
    with tempfile.TemporaryDirectory(dir=os.environ.get('VE_TMP')) as tmp:
        shutil.copytree(tpl,tmp,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.ready'))
        jf=Path(tmp)/'jobs.json'
        jf.write_text(json.dumps([{**j,'steps':[[OP[m],props(m,v)] for m,v in j['steps']]} for j in jobs]))
        for j in jobs:Path(j['out']).unlink(missing_ok=True)
        cmd=f"JOB_FILE={str(jf)!r};exec(open({str(BATCH)!r}).read())"
        r=subprocess.run([str(APPRUN),'-i','-n','--no-fonts','-d','--quit','--batch-interpreter','python-fu-eval','-b',cmd],
                         capture_output=True,text=True,timeout=timeout,cwd=tmp,env={**os.environ,'HOME':tmp})
        res=Path(str(jf)+'.result.json')
        if not res.exists():raise RuntimeError('gimp-console failed: '+r.stdout[-800:]+r.stderr[-800:])
        err=json.loads(res.read_text())['errors']
        # file_save can report success without a file (e.g. missing output directory)
        return {**{j['out']:'no output written' for j in jobs if not Path(j['out']).exists()},**err}

def render_steps(src,steps,out,size):
    err=run_batch([{'src':str(src),'out':str(out),'size':size,'steps':steps}])
    if err:raise RuntimeError(next(iter(err.values())))
    return out
